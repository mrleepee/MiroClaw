"""
Ontology Generation Service
Interface 1: Analyzes text content and generates entity and relationship type definitions suitable for social simulation
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# Valid base types for actor entities (from FOAF ontology)
ACTOR_BASE_TYPES = {"Person", "Organization", "Group"}

# Valid base types for context entities (from Schema.org)
CONTEXT_BASE_TYPES = {"CreativeWork", "Event", "Place", "Intangible"}

# All valid base types
ALL_BASE_TYPES = ACTOR_BASE_TYPES | CONTEXT_BASE_TYPES

# System prompt for ontology generation
ONTOLOGY_SYSTEM_PROMPT = """You are a knowledge graph ontology designer. Your task is to analyze text content and design entity types for a **social media simulation knowledge graph**.

**Important: You must output valid JSON only, nothing else.**

## Background

We are building a knowledge graph that serves two purposes:
1. **Actor entities** become simulated social media agents (they post, reply, and interact)
2. **Context entities** enrich the graph with places, events, documents, and concepts that actors reference

This separation is critical. Not everything in a document should become a social media account. Legal articles, historical events, and geographic locations are valuable graph context — but they do not tweet.

## Ontology Standards

Every entity type you create must declare a `base_type` from one of these standard ontologies:

### Actor Base Types (FOAF — these entities become simulation agents)
- **Person**: Any individual human (public figures, experts, citizens, officials)
- **Organization**: Any institution, company, government body, media outlet, NGO
- **Group**: Any collective of people with shared purpose (coalitions, movements, committees)

### Context Base Types (Schema.org — these entities stay in the graph as context)
- **CreativeWork**: Documents, articles, legislation, reports, publications, contracts
- **Event**: Proceedings, elections, referendums, hearings, conferences, incidents
- **Place**: Geographic locations, jurisdictions, facilities, venues
- **Intangible**: Abstract but identifiable concepts — legal principles, policies, standards, frameworks

## Output Format

```json
{
    "entity_types": [
        {
            "name": "TypeName (English, PascalCase)",
            "base_type": "Person|Organization|Group|CreativeWork|Event|Place|Intangible",
            "category": "actor|context",
            "description": "Brief description (English, max 100 chars)",
            "attributes": [
                {"name": "attr_name (snake_case)", "type": "text", "description": "..."}
            ],
            "examples": ["Example 1", "Example 2"]
        }
    ],
    "edge_types": [
        {
            "name": "RELATIONSHIP_NAME (UPPER_SNAKE_CASE)",
            "description": "Brief description (English, max 100 chars)",
            "source_targets": [
                {"source": "SourceType", "target": "TargetType"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Brief analysis of text content"
}
```

## Design Rules

### Entity Types

**Actor types (8-12 types, base_type = Person | Organization | Group, category = "actor"):**
- Create domain-specific subtypes of Person, Organization, or Group
- These represent real subjects who can hold opinions and interact on social media
- Must include fallback types: `Person` (base_type: Person) and `Organization` (base_type: Organization)
- Examples: Judge (Person), Senator (Person), MediaOutlet (Organization), PoliticalParty (Organization)

**Context types (4-8 types, base_type = CreativeWork | Event | Place | Intangible, category = "context"):**
- Create domain-specific subtypes for non-actor entities found in the text
- These represent things that actors reference, discuss, or are connected to
- Must include fallback type: `Thing` (base_type: Intangible, category: context) for anything that doesn't fit a more specific context type
- Examples: ConstitutionalArticle (CreativeWork), Referendum (Event), CourtHouse (Place)

**Key principle**: If an entity cannot plausibly have a social media account, it MUST be a context type. Legal articles, laws, processes, abstract roles (e.g., "Defendant"), unnamed persons, and concepts are context — never actors.

### Relationship Types
- Design 6-12 relationship types
- Relationships can connect any types — actor-to-actor, actor-to-context, or context-to-context
- Actor-to-context relationships are especially valuable (e.g., Judge INTERPRETS ConstitutionalArticle)
- Attribute names cannot use reserved words: `name`, `uuid`, `group_id`, `created_at`, `summary`

### Attributes
- 1-3 key attributes per entity type
- Use snake_case names
- Cannot use reserved words: `name`, `uuid`, `group_id`, `created_at`, `summary`

## Actor Type Reference

**Person subtypes**: Student, Professor, Journalist, Celebrity, Executive, Official, Lawyer, Doctor, Politician, Activist, Investor, Scientist
**Organization subtypes**: University, Company, GovernmentAgency, MediaOutlet, Hospital, NGO, Court, PoliticalParty, RegulatoryBody
**Group subtypes**: Committee, Coalition, Movement, Caucus, TaskForce

## Context Type Reference

**CreativeWork subtypes**: Legislation, Contract, Report, Publication, Policy, ConstitutionalArticle, LegalBrief
**Event subtypes**: Election, Trial, Hearing, Referendum, Conference, Protest, Investigation
**Place subtypes**: Country, City, Court, Parliament, Embassy, Territory
**Intangible subtypes**: LegalPrinciple, Regulation, Standard, Framework, Right, Obligation

## Relationship Type Reference

- WORKS_FOR, AFFILIATED_WITH, REPRESENTS, REGULATES, REPORTS_ON
- SUPPORTS, OPPOSES, COLLABORATES_WITH, COMPETES_WITH
- AUTHORED, INTERPRETS, REFERENCES, GOVERNS, LOCATED_IN, PARTICIPATES_IN
"""


class OntologyGenerator:
    """
    Ontology Generator
    Analyzes text content and generates entity and relationship type definitions
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate ontology definition

        Args:
            document_texts: List of document texts
            simulation_requirement: Simulation requirement description
            additional_context: Additional context

        Returns:
            Ontology definition (entity_types, edge_types, etc.)
        """
        # Build user message
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # Call LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )

        # Validate and post-process
        result = self._validate_and_process(result)
        
        return result
    
    # Maximum text length for LLM (50,000 characters)
    MAX_TEXT_LENGTH_FOR_LLM = 50000

    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Build user message"""

        # Combine texts
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        # If text exceeds 50,000 characters, truncate (only affects content sent to LLM, not graph building)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Original text is {original_length} characters, truncated to first {self.MAX_TEXT_LENGTH_FOR_LLM} characters for ontology analysis)..."
        
        message = f"""## Simulation Requirements

{simulation_requirement}

## Document Content

{combined_text}
"""

        if additional_context:
            message += f"""
## Additional Notes

{additional_context}
"""

        message += """
Design entity types and relationship types for this scenario.

**Rules**:
1. Create 8-12 **actor** types (base_type: Person, Organization, or Group; category: "actor"). These become social media agents.
2. Create 4-8 **context** types (base_type: CreativeWork, Event, Place, or Intangible; category: "context"). These stay in the graph as context.
3. Must include fallback types: Person (actor), Organization (actor), Thing (context with base_type Intangible).
4. Every type must declare `base_type` and `category`.
5. If an entity cannot have a social media account, it MUST be a context type.
6. Attribute names cannot use reserved words: name, uuid, group_id, created_at, summary.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and post-process results, ensuring actor/context classification."""

        # Ensure required fields exist
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""

        # Validate and normalize entity types
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."

            # Ensure base_type and category are present and valid
            base_type = entity.get("base_type", "")
            if base_type in ACTOR_BASE_TYPES:
                entity["base_type"] = base_type
                entity["category"] = "actor"
            elif base_type in CONTEXT_BASE_TYPES:
                entity["base_type"] = base_type
                entity["category"] = "context"
            else:
                # Infer category from type name heuristics; override invalid base_type
                entity["category"] = self._infer_category(entity)
                if entity["category"] == "actor":
                    entity["base_type"] = "Person"
                else:
                    entity["base_type"] = "Intangible"

        # Validate relationship types
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."

        # Max limits for Neo4j label performance
        MAX_ENTITY_TYPES = 20
        MAX_EDGE_TYPES = 15

        # Ensure required fallback types exist
        self._ensure_fallback_types(result)

        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]

        return result

    @staticmethod
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

    @staticmethod
    def _ensure_fallback_types(result: Dict[str, Any]) -> None:
        """Ensure Person (actor), Organization (actor), and Thing (context) fallbacks exist."""
        entity_names = {e["name"] for e in result["entity_types"]}

        fallbacks = []
        if "Person" not in entity_names:
            fallbacks.append({
                "name": "Person",
                "base_type": "Person",
                "category": "actor",
                "description": "Any individual person not fitting more specific person types.",
                "attributes": [
                    {"name": "full_name", "type": "text", "description": "Full name"},
                    {"name": "role", "type": "text", "description": "Role or occupation"},
                ],
                "examples": ["ordinary citizen", "unnamed individual"],
            })
        if "Organization" not in entity_names:
            fallbacks.append({
                "name": "Organization",
                "base_type": "Organization",
                "category": "actor",
                "description": "Any organization not fitting more specific organization types.",
                "attributes": [
                    {"name": "org_name", "type": "text", "description": "Organization name"},
                    {"name": "org_type", "type": "text", "description": "Type of organization"},
                ],
                "examples": ["small business", "community group"],
            })
        if "Thing" not in entity_names:
            fallbacks.append({
                "name": "Thing",
                "base_type": "Intangible",
                "category": "context",
                "description": "Any context entity not fitting more specific context types.",
                "attributes": [
                    {"name": "thing_type", "type": "text", "description": "Type or classification"},
                ],
                "examples": ["legal concept", "abstract framework"],
            })

        result["entity_types"].extend(fallbacks)
    
    @staticmethod
    def get_actor_type_names(ontology: Dict[str, Any]) -> List[str]:
        """Return names of entity types classified as actors."""
        return [
            et["name"]
            for et in ontology.get("entity_types", [])
            if et.get("category") == "actor"
        ]

    @staticmethod
    def get_context_type_names(ontology: Dict[str, Any]) -> List[str]:
        """Return names of entity types classified as context."""
        return [
            et["name"]
            for et in ontology.get("entity_types", [])
            if et.get("category") == "context"
        ]

    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Convert ontology definition to Python code (similar to ontology.py)

        Args:
            ontology: Ontology definition

        Returns:
            Python code string
        """
        code_lines = [
            '"""',
            'Custom entity type definitions',
            'Auto-generated by MiroFish (FOAF/Schema.org standards-based ontology)',
            '"""',
            '',
            'from pydantic import Field',
            '# Note: LocalGraphService uses dict-based ontology, not Zep models',
            '',
            '',
            '# ============== Entity Type Definitions ==============',
            '',
        ]

        # Generate entity types
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")

            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        code_lines.append('# ============== Relationship Type Definitions ==============')
        code_lines.append('')

        # Generate relationship types
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Convert to PascalCase class name
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")

            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        # Generate type dictionaries
        code_lines.append('# ============== Type Configuration ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')

        # Generate edge source_targets mapping
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

