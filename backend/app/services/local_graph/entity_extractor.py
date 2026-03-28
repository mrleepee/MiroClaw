"""LLM-based entity and relationship extraction from text chunks."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an entity and relationship extraction engine.
Given an ontology definition and a text chunk, extract entities and relationships
that match the ontology types.

The ontology contains two categories of entity types:
- **Actor types** (category: "actor"): People, organizations, and groups that can hold opinions and interact on social media. These will become simulation agents.
- **Context types** (category: "context"): Documents, events, places, and concepts that provide context. These enrich the knowledge graph but do not become agents.

Rules:
- Only extract entities whose type matches one of the defined entity_types
- Only extract relationships whose type matches one of the defined edge_types
- Choose the most specific matching type for each entity
- Use context types for non-actor entities (legal articles, laws, processes, places, events, abstract concepts) — do NOT force these into Person or Organization
- Use actor fallback types (Person, Organization) only for actual people or organisations that lack a more specific actor type
- Each entity must have a name and a type
- Each relationship must reference source and target entities by name and have a type and fact
- If an entity has attributes defined in the ontology, extract those attribute values from the text
- Extract entities that are relevant to the scenario and have clear identities in the text
- Do not invent entities or relationships not supported by the text

Return valid JSON in this exact format:
{
  "entities": [
    {
      "name": "Entity Name",
      "type": "EntityType",
      "summary": "Brief description based on the text",
      "attributes": {"attr1": "value1"}
    }
  ],
  "relationships": [
    {
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "RELATIONSHIP_TYPE",
      "fact": "Description of the relationship"
    }
  ]
}"""


class EntityExtractor:
    """Extracts entities and relationships from text using an LLM."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: An LLMClient instance with chat_json() method.
        """
        self._llm = llm_client

    def extract(
        self,
        text: str,
        ontology: Dict[str, Any],
        existing_entity_names: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract entities and relationships from a text chunk.

        Args:
            text: The text chunk to process.
            ontology: Ontology definition with entity_types and edge_types.
            existing_entity_names: Names of entities already in the graph,
                for deduplication hints.

        Returns:
            Dict with "entities" and "relationships" lists.
        """
        if not text or not text.strip():
            return {"entities": [], "relationships": []}

        user_prompt = self._build_user_prompt(text, ontology, existing_entity_names)

        try:
            result = self._llm.chat_json(
                messages=[
                    {"role": "user", "content": EXTRACTION_SYSTEM_PROMPT + "\n\n" + user_prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            return self._validate_result(result, ontology)
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {"entities": [], "relationships": []}

    def _build_user_prompt(
        self,
        text: str,
        ontology: Dict[str, Any],
        existing_entity_names: Optional[List[str]] = None,
    ) -> str:
        parts = [
            "## Ontology Definition",
            f"```json\n{json.dumps(ontology, indent=2, ensure_ascii=False)}\n```",
            "",
            "## Text to Analyze",
            f"```\n{text}\n```",
        ]

        if existing_entity_names:
            parts.extend([
                "",
                "## Existing Entities in Graph (for deduplication)",
                "If you find entities matching these names, use the exact same name:",
                ", ".join(existing_entity_names[:50]),
            ])

        return "\n".join(parts)

    def _validate_result(
        self, result: Dict[str, Any], ontology: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Validate and clean extraction results, propagating category from ontology."""
        entities = result.get("entities", [])
        relationships = result.get("relationships", [])

        entity_type_defs = ontology.get("entity_types", {})
        valid_entity_types = set(entity_type_defs.keys())
        valid_edge_types = set(ontology.get("edge_types", {}).keys())

        # Guard: warn if ontology is empty (indicates loading bug)
        if not entity_type_defs:
            logger.warning("entity_type_defs is empty - ontology may not be loaded correctly")

        # Filter entities to valid types, propagate category
        valid_entities = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = entity.get("name", "").strip()
            etype = entity.get("type", "").strip()
            if name and (not valid_entity_types or etype in valid_entity_types):
                # Look up category from ontology definition
                type_def = entity_type_defs.get(etype, {})
                if not type_def and etype:
                    logger.warning(f"Type '{etype}' not found in ontology for entity '{name}', defaulting to 'actor'")
                category = type_def.get("category", "actor")
                valid_entities.append({
                    "name": name,
                    "type": etype,
                    "summary": entity.get("summary", ""),
                    "attributes": entity.get("attributes", {}),
                    "category": category,
                })

        # Filter relationships to valid types
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
                    valid_rels.append({
                        "source": source,
                        "target": target,
                        "type": rtype,
                        "fact": fact,
                    })

        return {"entities": valid_entities, "relationships": valid_rels}
