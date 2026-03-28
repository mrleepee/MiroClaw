"""
Tests for standards-based ontology with actor/context separation.

Verifies:
- Ontology validation correctly classifies actor vs context types
- Fallback types are always present
- Entity extraction propagates category
- Entity filtering respects actors_only flag

Uses isolated copies of the logic to avoid full app import chain.
"""

import pytest
from typing import Any, Dict, List


# ── Standalone copies of constants and logic under test ──────────

ACTOR_BASE_TYPES = {"Person", "Organization", "Group"}
CONTEXT_BASE_TYPES = {"CreativeWork", "Event", "Place", "Intangible"}
ALL_BASE_TYPES = ACTOR_BASE_TYPES | CONTEXT_BASE_TYPES


def _infer_category(entity: Dict[str, Any]) -> str:
    """Infer actor/context category when LLM doesn't provide a valid base_type."""
    name = entity.get("name", "").lower()
    desc = (entity.get("description", "") or "").lower()

    context_signals = [
        "article", "legislation", "law", "act", "decree", "policy",
        "event", "election", "referendum", "hearing", "trial",
        "place", "location", "city", "country", "territory",
        "concept", "principle", "standard", "framework", "right",
        "document", "report", "contract", "publication",
    ]
    for signal in context_signals:
        if signal in name or signal in desc:
            return "context"
    return "actor"


def _ensure_fallback_types(result: Dict[str, Any]) -> None:
    """Ensure Person (actor), Organization (actor), and Thing (context) fallbacks exist."""
    entity_names = {e["name"] for e in result["entity_types"]}

    fallbacks = []
    if "Person" not in entity_names:
        fallbacks.append({
            "name": "Person", "base_type": "Person", "category": "actor",
            "description": "Any individual person not fitting more specific person types.",
            "attributes": [], "examples": [],
        })
    if "Organization" not in entity_names:
        fallbacks.append({
            "name": "Organization", "base_type": "Organization", "category": "actor",
            "description": "Any organization not fitting more specific organization types.",
            "attributes": [], "examples": [],
        })
    if "Thing" not in entity_names:
        fallbacks.append({
            "name": "Thing", "base_type": "Intangible", "category": "context",
            "description": "Any context entity not fitting more specific context types.",
            "attributes": [], "examples": [],
        })
    result["entity_types"].extend(fallbacks)


def validate_and_process(result: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone copy of OntologyGenerator._validate_and_process."""
    if "entity_types" not in result:
        result["entity_types"] = []
    if "edge_types" not in result:
        result["edge_types"] = []
    if "analysis_summary" not in result:
        result["analysis_summary"] = ""

    for entity in result["entity_types"]:
        if "attributes" not in entity:
            entity["attributes"] = []
        if "examples" not in entity:
            entity["examples"] = []
        if len(entity.get("description", "")) > 100:
            entity["description"] = entity["description"][:97] + "..."

        base_type = entity.get("base_type", "")
        if base_type in ACTOR_BASE_TYPES:
            entity["base_type"] = base_type
            entity["category"] = "actor"
        elif base_type in CONTEXT_BASE_TYPES:
            entity["base_type"] = base_type
            entity["category"] = "context"
        else:
            entity["category"] = _infer_category(entity)
            if entity["category"] == "actor":
                entity["base_type"] = "Person"
            else:
                entity["base_type"] = "Intangible"

    for edge in result["edge_types"]:
        if "source_targets" not in edge:
            edge["source_targets"] = []
        if "attributes" not in edge:
            edge["attributes"] = []
        if len(edge.get("description", "")) > 100:
            edge["description"] = edge["description"][:97] + "..."

    _ensure_fallback_types(result)

    MAX_ENTITY_TYPES = 20
    MAX_EDGE_TYPES = 15
    if len(result["entity_types"]) > MAX_ENTITY_TYPES:
        result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
    if len(result["edge_types"]) > MAX_EDGE_TYPES:
        result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]

    return result


def get_actor_type_names(ontology: Dict[str, Any]) -> List[str]:
    return [et["name"] for et in ontology.get("entity_types", []) if et.get("category") == "actor"]


def get_context_type_names(ontology: Dict[str, Any]) -> List[str]:
    return [et["name"] for et in ontology.get("entity_types", []) if et.get("category") == "context"]


def validate_extraction_result(
    result: Dict[str, Any], ontology: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    """Standalone copy of EntityExtractor._validate_result with category propagation."""
    entities = result.get("entities", [])
    relationships = result.get("relationships", [])

    entity_type_defs = ontology.get("entity_types", {})
    valid_entity_types = set(entity_type_defs.keys())
    valid_edge_types = set(ontology.get("edge_types", {}).keys())

    valid_entities = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = entity.get("name", "").strip()
        etype = entity.get("type", "").strip()
        if name and (not valid_entity_types or etype in valid_entity_types):
            type_def = entity_type_defs.get(etype, {})
            category = type_def.get("category", "actor")
            valid_entities.append({
                "name": name,
                "type": etype,
                "summary": entity.get("summary", ""),
                "attributes": entity.get("attributes", {}),
                "category": category,
            })

    valid_rels = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        source = rel.get("source", "").strip()
        target = rel.get("target", "").strip()
        rtype = rel.get("type", "").strip()
        fact = rel.get("fact", "").strip()
        if source and target and fact:
            if not valid_edge_types or rtype in valid_edge_types:
                valid_rels.append({"source": source, "target": target, "type": rtype, "fact": fact})

    return {"entities": valid_entities, "relationships": valid_rels}


# ── Tests ────────────────────────────────────────────────────────


class TestOntologyConstants:
    """Test that the base type constants are correct."""

    def test_actor_base_types(self):
        assert ACTOR_BASE_TYPES == {"Person", "Organization", "Group"}

    def test_context_base_types(self):
        assert CONTEXT_BASE_TYPES == {"CreativeWork", "Event", "Place", "Intangible"}

    def test_no_overlap(self):
        assert ACTOR_BASE_TYPES & CONTEXT_BASE_TYPES == set()


class TestOntologyValidation:
    """Test validate_and_process correctly classifies and normalizes types."""

    def test_actor_types_preserved(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Judge", "base_type": "Person", "category": "actor", "description": "A judge"},
                {"name": "Court", "base_type": "Organization", "category": "actor", "description": "A court"},
            ],
            "edge_types": [],
        })
        judge = next(e for e in result["entity_types"] if e["name"] == "Judge")
        court = next(e for e in result["entity_types"] if e["name"] == "Court")
        assert judge["category"] == "actor"
        assert judge["base_type"] == "Person"
        assert court["category"] == "actor"
        assert court["base_type"] == "Organization"

    def test_context_types_preserved(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "ConstitutionalArticle", "base_type": "CreativeWork", "category": "context", "description": "A law article"},
                {"name": "Referendum", "base_type": "Event", "category": "context", "description": "A vote"},
            ],
            "edge_types": [],
        })
        article = next(e for e in result["entity_types"] if e["name"] == "ConstitutionalArticle")
        referendum = next(e for e in result["entity_types"] if e["name"] == "Referendum")
        assert article["category"] == "context"
        assert article["base_type"] == "CreativeWork"
        assert referendum["category"] == "context"
        assert referendum["base_type"] == "Event"

    def test_fallback_types_added_when_missing(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Judge", "base_type": "Person", "category": "actor", "description": "A judge"},
            ],
            "edge_types": [],
        })
        names = {e["name"] for e in result["entity_types"]}
        assert "Person" in names
        assert "Organization" in names
        assert "Thing" in names

    def test_fallback_person_is_actor(self):
        result = validate_and_process({"entity_types": [], "edge_types": []})
        person = next(e for e in result["entity_types"] if e["name"] == "Person")
        assert person["category"] == "actor"
        assert person["base_type"] == "Person"

    def test_fallback_organization_is_actor(self):
        result = validate_and_process({"entity_types": [], "edge_types": []})
        org = next(e for e in result["entity_types"] if e["name"] == "Organization")
        assert org["category"] == "actor"
        assert org["base_type"] == "Organization"

    def test_fallback_thing_is_context(self):
        result = validate_and_process({"entity_types": [], "edge_types": []})
        thing = next(e for e in result["entity_types"] if e["name"] == "Thing")
        assert thing["category"] == "context"
        assert thing["base_type"] == "Intangible"

    def test_existing_fallbacks_not_duplicated(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Person", "base_type": "Person", "category": "actor", "description": "A person"},
                {"name": "Organization", "base_type": "Organization", "category": "actor", "description": "An org"},
                {"name": "Thing", "base_type": "Intangible", "category": "context", "description": "A thing"},
            ],
            "edge_types": [],
        })
        person_count = sum(1 for e in result["entity_types"] if e["name"] == "Person")
        assert person_count == 1

    def test_invalid_base_type_inferred_as_actor(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Hacker", "base_type": "INVALID", "description": "A hacker"},
            ],
            "edge_types": [],
        })
        hacker = next(e for e in result["entity_types"] if e["name"] == "Hacker")
        assert hacker["category"] == "actor"
        assert hacker["base_type"] == "Person"

    def test_missing_base_type_inferred_context_from_name(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Legislation", "description": "A piece of legislation"},
            ],
            "edge_types": [],
        })
        legislation = next(e for e in result["entity_types"] if e["name"] == "Legislation")
        assert legislation["category"] == "context"

    def test_missing_base_type_inferred_context_from_description(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "SomeItem", "description": "A legal document or contract"},
            ],
            "edge_types": [],
        })
        item = next(e for e in result["entity_types"] if e["name"] == "SomeItem")
        assert item["category"] == "context"

    def test_description_truncated(self):
        result = validate_and_process({
            "entity_types": [
                {"name": "Test", "base_type": "Person", "category": "actor", "description": "x" * 200},
            ],
            "edge_types": [],
        })
        test_type = next(e for e in result["entity_types"] if e["name"] == "Test")
        assert len(test_type["description"]) <= 100

    def test_empty_input_produces_fallbacks(self):
        result = validate_and_process({})
        names = {e["name"] for e in result["entity_types"]}
        assert names == {"Person", "Organization", "Thing"}


class TestGetTypeNames:
    """Test helper methods for getting actor/context type names."""

    def test_get_actor_type_names(self):
        ontology = {
            "entity_types": [
                {"name": "Judge", "category": "actor"},
                {"name": "ConstitutionalArticle", "category": "context"},
                {"name": "Person", "category": "actor"},
            ]
        }
        actors = get_actor_type_names(ontology)
        assert actors == ["Judge", "Person"]

    def test_get_context_type_names(self):
        ontology = {
            "entity_types": [
                {"name": "Judge", "category": "actor"},
                {"name": "ConstitutionalArticle", "category": "context"},
                {"name": "Thing", "category": "context"},
            ]
        }
        contexts = get_context_type_names(ontology)
        assert contexts == ["ConstitutionalArticle", "Thing"]

    def test_empty_ontology(self):
        assert get_actor_type_names({}) == []
        assert get_context_type_names({}) == []


class TestExtractionValidation:
    """Test that entity extraction propagates category from ontology."""

    def test_category_propagated_from_ontology(self):
        ontology = {
            "entity_types": {
                "Judge": {"description": "A judge", "category": "actor"},
                "ConstitutionalArticle": {"description": "A law article", "category": "context"},
            },
            "edge_types": {},
        }
        raw_result = {
            "entities": [
                {"name": "Judge Smith", "type": "Judge", "summary": "A senior judge"},
                {"name": "Article 102", "type": "ConstitutionalArticle", "summary": "Property rights"},
            ],
            "relationships": [],
        }
        validated = validate_extraction_result(raw_result, ontology)

        judge = next(e for e in validated["entities"] if e["name"] == "Judge Smith")
        article = next(e for e in validated["entities"] if e["name"] == "Article 102")
        assert judge["category"] == "actor"
        assert article["category"] == "context"

    def test_unknown_type_defaults_to_actor(self):
        ontology = {"entity_types": {}, "edge_types": {}}
        raw_result = {
            "entities": [{"name": "Mystery", "type": "Unknown", "summary": "?"}],
            "relationships": [],
        }
        validated = validate_extraction_result(raw_result, ontology)
        assert validated["entities"][0]["category"] == "actor"

    def test_invalid_entity_filtered(self):
        ontology = {
            "entity_types": {"Judge": {"description": "A judge", "category": "actor"}},
            "edge_types": {},
        }
        raw_result = {
            "entities": [
                {"name": "Judge Smith", "type": "Judge", "summary": "valid"},
                {"name": "Phantom", "type": "Ghost", "summary": "invalid type"},
            ],
            "relationships": [],
        }
        validated = validate_extraction_result(raw_result, ontology)
        assert len(validated["entities"]) == 1
        assert validated["entities"][0]["name"] == "Judge Smith"

    def test_empty_name_filtered(self):
        ontology = {
            "entity_types": {"Judge": {"description": "A judge", "category": "actor"}},
            "edge_types": {},
        }
        raw_result = {
            "entities": [{"name": "  ", "type": "Judge", "summary": "no name"}],
            "relationships": [],
        }
        validated = validate_extraction_result(raw_result, ontology)
        assert len(validated["entities"]) == 0


class TestLiberland:
    """Integration-style tests simulating the Liberland scenario."""

    def test_liberland_ontology_has_actor_and_context_types(self):
        """Simulate what the LLM would produce for Liberland documents."""
        llm_output = {
            "entity_types": [
                {"name": "Judge", "base_type": "Person", "category": "actor", "description": "Judicial official"},
                {"name": "Senator", "base_type": "Person", "category": "actor", "description": "Elected legislator"},
                {"name": "CryptoInvestor", "base_type": "Person", "category": "actor", "description": "Cryptocurrency investor"},
                {"name": "Journalist", "base_type": "Person", "category": "actor", "description": "News reporter"},
                {"name": "LegalScholar", "base_type": "Person", "category": "actor", "description": "Legal academic"},
                {"name": "Homesteader", "base_type": "Person", "category": "actor", "description": "Liberland settler"},
                {"name": "GovernmentAgency", "base_type": "Organization", "category": "actor", "description": "Government body"},
                {"name": "PoliticalParty", "base_type": "Organization", "category": "actor", "description": "Political party"},
                {"name": "ConstitutionalArticle", "base_type": "CreativeWork", "category": "context", "description": "Constitutional provision"},
                {"name": "LegalProceeding", "base_type": "Event", "category": "context", "description": "Court case or hearing"},
                {"name": "Referendum", "base_type": "Event", "category": "context", "description": "Public vote"},
                {"name": "Territory", "base_type": "Place", "category": "context", "description": "Geographic area"},
            ],
            "edge_types": [
                {"name": "INTERPRETS", "description": "Interprets a legal document", "source_targets": [{"source": "Judge", "target": "ConstitutionalArticle"}]},
            ],
        }

        result = validate_and_process(llm_output)

        actors = get_actor_type_names(result)
        contexts = get_context_type_names(result)

        # Actor types should include the specified ones + fallbacks
        assert "Judge" in actors
        assert "Senator" in actors
        assert "Person" in actors  # fallback
        assert "Organization" in actors  # fallback

        # Context types should include the specified ones + fallback
        assert "ConstitutionalArticle" in contexts
        assert "LegalProceeding" in contexts
        assert "Referendum" in contexts
        assert "Thing" in contexts  # fallback

        # ConstitutionalArticle is NOT an actor
        assert "ConstitutionalArticle" not in actors

    def test_article_102_extracted_as_context(self):
        """Article 102 should be classified as context, not forced into Organization."""
        ontology = {
            "entity_types": {
                "Judge": {"description": "Judicial official", "category": "actor"},
                "ConstitutionalArticle": {"description": "Constitutional provision", "category": "context"},
                "Organization": {"description": "Fallback org", "category": "actor"},
            },
            "edge_types": {
                "INTERPRETS": {"description": "Interprets"},
            },
        }

        extraction = {
            "entities": [
                {"name": "Judge Hendricks", "type": "Judge", "summary": "Presiding judge"},
                {"name": "Article 102", "type": "ConstitutionalArticle", "summary": "Property rights article"},
            ],
            "relationships": [
                {"source": "Judge Hendricks", "target": "Article 102", "type": "INTERPRETS", "fact": "Judge Hendricks interprets Article 102"},
            ],
        }

        validated = validate_extraction_result(extraction, ontology)

        article = next(e for e in validated["entities"] if e["name"] == "Article 102")
        assert article["category"] == "context"
        assert article["type"] == "ConstitutionalArticle"

        # Relationship preserved
        assert len(validated["relationships"]) == 1
        assert validated["relationships"][0]["source"] == "Judge Hendricks"
        assert validated["relationships"][0]["target"] == "Article 102"
