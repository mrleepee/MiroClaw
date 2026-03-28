"""
OASIS Agent Profile Generator
Convert entities in the Neo4j graph into the Agent Profile format required by the OASIS simulation platform.

Optimizations:
1. Call graph retrieval to further enrich node information
2. Optimize prompts to generate highly detailed personas
3. Distinguish individual entities from abstract group entities
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .graph_entity_reader import EntityNode, GraphEntityReader
from .graph_builder import get_graph_service

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Optional fields - Reddit style
    karma: int = 1000
    
    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Additional persona information
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Source entity information
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # The OASIS library requires the field name to be username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
            # OASIS-required fields: always include with defaults
            "age": self.age if self.age else 30,
            "gender": self.gender if self.gender else "other",
            "mbti": self.mbti if self.mbti else "ISTJ",
            "country": self.country if self.country else "Unknown",
        }
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # The OASIS library requires the field name to be username (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
            # OASIS-required fields: always include with defaults
            "age": self.age if self.age else 30,
            "gender": self.gender if self.gender else "other",
            "mbti": self.mbti if self.mbti else "ISTJ",
            "country": self.country if self.country else "Unknown",
        }
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dictionary format."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator
    
    Convert entities in the Neo4j graph into the Agent Profile format required by the OASIS simulation.
    
    Optimized features:
    1. Use Neo4j graph retrieval to obtain richer context
    2. Generate highly detailed personas (including basic info, career history, personality traits, social media behavior, etc.)
    3. Distinguish individual entities from abstract group entities
    """
    
    # MBTI type list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Common country list
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individual entity types (require concrete personas)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Group/institution entity types (require representative account personas)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # Graph service for retrieving rich context
        self.graph_id = graph_id
        self.graph_service = get_graph_service()
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Generate an OASIS Agent Profile from a graph entity.
        
        Args:
            entity: graph entity node
            user_id: User ID (for OASIS)
            use_llm: Whether to use the LLM to generate a detailed persona
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Basic information
        name = entity.name
        user_name = self._generate_username(name)
        
        # Build context information
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Use the LLM to generate a detailed persona
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Use rules to generate a basic persona
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Generate a username."""
        # Remove special characters and convert to lowercase
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Add a random suffix to avoid duplicates
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_graph_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Use graph search to retrieve rich information related to an entity.

        Uses LocalGraphService search to find related edges and nodes.

        Args:
            entity: Entity node object

        Returns:
            A dictionary containing facts, node_summaries, and context
        """
        entity_name = entity.name

        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }

        # A graph_id is required before search can run
        if not self.graph_id:
            logger.debug("Skipping graph retrieval: graph_id is not set")
            return results

        comprehensive_query = f"All information, activities, events, relationships, and background about {entity_name}"

        try:
            # Search for edges (facts/relationships)
            edge_result = self.graph_service.search(
                graph_id=self.graph_id,
                query=comprehensive_query,
                limit=30,
                scope="edges"
            )

            # Search for nodes (entity summaries)
            node_result = self.graph_service.search(
                graph_id=self.graph_id,
                query=comprehensive_query,
                limit=20,
                scope="nodes"
            )

            # Process edge search results
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)

            # Process node search results
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"Related entity: {node.name}")
            results["node_summaries"] = list(all_summaries)

            # Build combined context
            context_parts = []
            if results["facts"]:
                context_parts.append("Facts:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)

            logger.info(
                f"Graph retrieval completed: {entity_name}, "
                f"retrieved {len(results['facts'])} facts and {len(results['node_summaries'])} related nodes"
            )

        except Exception as e:
            logger.warning(f"Graph retrieval failed ({entity_name}): {e}")

        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Build the full context information for an entity.
        
        Includes:
        1. Edge information for the entity itself (facts)
        2. Detailed information from connected nodes
        3. Rich information retrieved via graph hybrid search
        """
        context_parts = []
        
        # 1. Add entity attribute information
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity Attributes\n" + "\n".join(attrs))
        
        # 2. Add related edge information (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # No quantity limit
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (related entity)")
                    else:
                        relationships.append(f"- (related entity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Related Facts and Relationships\n" + "\n".join(relationships))
        
        # 3. Add detailed information for connected nodes, grouped by category
        if entity.related_nodes:
            actor_nodes = []
            context_nodes = []
            for node in entity.related_nodes:  # No quantity limit
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                node_category = node.get("entity_category", "actor")

                # Filter out default labels
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""

                entry = f"- **{node_name}**{label_str}: {node_summary}" if node_summary else f"- **{node_name}**{label_str}"

                if node_category == "context":
                    context_nodes.append(entry)
                else:
                    actor_nodes.append(entry)

            if actor_nodes:
                context_parts.append("### Connected People and Organizations\n" + "\n".join(actor_nodes))
            if context_nodes:
                context_parts.append("### Related Documents, Events, and Context\n" + "\n".join(context_nodes))
        
        # 4. Use Zep hybrid retrieval to get richer information
        graph_results = self._search_graph_for_entity(entity)
        
        if graph_results.get("facts"):
            # De-duplicate by excluding existing facts
            new_facts = [f for f in graph_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Facts Retrieved from the graph\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if graph_results.get("node_summaries"):
            context_parts.append("### Related Nodes Retrieved from the graph\n" + "\n".join(f"- {s}" for s in graph_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Check whether this is an individual entity."""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Check whether this is a group/institution entity."""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Use the LLM to generate a highly detailed persona.
        
        Different handling by entity type:
        - Individual entities: generate a concrete character profile
        - Group/institution entities: generate a representative account profile
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Try multiple times until success or the maximum retry count is reached
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Lower the temperature on each retry
                    # Do not set max_tokens so the LLM can respond freely
                )
                
                content = response.choices[0].message.content
                
                # Check whether the output was truncated (finish_reason is not "stop")
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM output was truncated (attempt {attempt+1}), trying to repair...")
                    content = self._fix_truncated_json(content)
                
                # Try parsing the JSON
                try:
                    result = json.loads(content)
                    
                    # Validate required fields
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON parsing failed (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # Try to repair the JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponential backoff
        
        logger.warning(
            f"LLM persona generation failed ({max_attempts} attempts): {last_error}, "
            "falling back to rule-based generation"
        )
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Repair truncated JSON that was cut off by max_tokens."""
        import re
        
        # If the JSON was truncated, try to close it
        content = content.strip()
        
        # Count unclosed braces and brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed strings
        # Simple check: if the ending character is not a quote/comma/closing brace,
        # the string may have been truncated
        if content and content[-1] not in '",}]':
            # Try to close the string
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Try to repair malformed JSON."""
        import re
        
        # 1. First try to repair truncation
        content = self._fix_truncated_json(content)
        
        # 2. Try to extract the JSON portion
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Handle newline issues inside strings
            # Find all string values and replace embedded newlines
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace literal newlines inside strings with spaces
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Collapse extra whitespace
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Match JSON string values
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Try parsing
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. If it still fails, try a more aggressive repair
                try:
                    # Remove all control characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Collapse all repeated whitespace
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Try extracting partial information from the content
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # May be truncated
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a {entity_type}.")
        
        # If meaningful content was extracted, mark it as repaired
        if bio_match or persona_match:
            logger.info("Extracted partial information from malformed JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Complete failure: return a base structure
        logger.warning("JSON repair failed, returning base structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a {entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Get the system prompt."""
        base_prompt = (
            "You are an expert in generating social media user profiles. Generate detailed "
            "and realistic personas for opinion simulation, matching known real-world "
            "conditions as closely as possible. You must return valid JSON, and all string "
            "values must not contain unescaped newline characters. Use English."
        )
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build the detailed persona prompt for an individual entity."""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"
        
        return f"""Generate a detailed social media user persona for the entity below, matching known real-world conditions as closely as possible.

Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context information:
{context_str}

Please generate JSON containing the following fields:

1. bio: Social media bio, 200 characters
2. persona: Detailed persona description (2000 characters of plain text), which must include:
   - Basic information (age, profession, educational background, location)
   - Personal background (important experiences, connection to events, social relationships)
   - Personality traits (MBTI type, core personality, emotional expression style)
   - Social media behavior (posting frequency, content preferences, interaction style, language patterns)
   - Positions and views (attitudes toward topics, content that may anger or move them)
   - Distinctive traits (catchphrases, unusual experiences, personal hobbies)
   - Personal memory (a key part of the persona: explain this individual's connection to the event, plus their existing actions and reactions in the event)
3. age: Numeric age (must be an integer)
4. gender: Gender, must be in English: "male" or "female"
5. mbti: MBTI type (such as INTJ, ENFP, etc.)
6. country: Country (use English, for example "China")
7. profession: Profession
8. interested_topics: Array of topics of interest

Important:
- All field values must be strings or numbers; do not use newline characters
- persona must be a single coherent block of text
- Use English (except the gender field, which must use English male/female)
- The content must remain consistent with the entity information
- age must be a valid integer, and gender must be "male" or "female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build the detailed persona prompt for a group/institution entity."""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"
        
        return f"""Generate a detailed social media account profile for the organization/group entity below, matching known real-world conditions as closely as possible.

Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context information:
{context_str}

Please generate JSON containing the following fields:

1. bio: Official account bio, 200 characters, professional and appropriate
2. persona: Detailed account profile description (2000 characters of plain text), which must include:
   - Basic organization information (official name, nature of the organization, founding background, primary functions)
   - Account positioning (account type, target audience, core functions)
   - Voice and speaking style (language characteristics, common expressions, taboo topics)
   - Publishing characteristics (content types, posting frequency, active time ranges)
   - Positions and attitudes (official stance on core topics, handling of controversies)
   - Special notes (the group profile represented, operating habits)
   - Institutional memory (a key part of the institutional persona: explain this organization's connection to the event, plus its existing actions and reactions in the event)
3. age: Always set to 30 (the virtual age of an institutional account)
4. gender: Always set to "other" (institutional accounts use other to indicate non-person)
5. mbti: MBTI type used to describe account style, e.g. ISTJ for rigorous and conservative
6. country: Country (use English, for example "China")
7. profession: Description of institutional function
8. interested_topics: Array of focus areas

Important:
- All field values must be strings or numbers; null values are not allowed
- persona must be a single coherent block of text; do not use newline characters
- Use English (except the gender field, which must use English "other")
- age must be the integer 30, and gender must be the string "other"
- The account's voice must match its institutional identity"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a basic persona using rules."""
        
        # Generate different personas based on entity type
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Virtual age for an institutional account
                "gender": "other",  # Institutions use "other"
                "mbti": "ISTJ",  # Institutional style: rigorous and conservative
                "country": "China",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Virtual age for an institutional account
                "gender": "other",  # Institutions use "other"
                "mbti": "ISTJ",  # Institutional style: rigorous and conservative
                "country": "China",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Default persona
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Set the graph ID used for graph retrieval."""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Batch-generate Agent Profiles from entities, with parallel generation support.
        
        Args:
            entities: List of entities
            use_llm: Whether to use the LLM to generate detailed personas
            progress_callback: Progress callback function (current, total, message)
            graph_id: Graph ID used for graph retrieval to obtain richer context
            parallel_count: Number of profiles to generate in parallel, default 5
            realtime_output_path: File path for real-time writes (if provided, write after each generated profile)
            output_platform: Output platform format ("reddit" or "twitter")
            
        Returns:
            List of Agent Profiles
        """
        import concurrent.futures
        from threading import Lock
        
        # Set graph_id for graph retrieval
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # Preallocate the list to preserve order
        completed_count = [0]  # Use a list so it can be mutated inside the closure
        lock = Lock()
        
        # Helper function for real-time file writes
        def save_profiles_realtime():
            """Persist generated profiles to file in real time."""
            if not realtime_output_path:
                return
            
            with lock:
                # Filter out generated profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Failed to save profiles in real time: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function that generates a single profile."""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Print the generated persona to the console in real time
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Failed to generate a persona for entity {entity.name}: {str(e)}")
                # Create a basic fallback profile with complete demographic fields
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                    age=30,  # Required default
                    gender="other",  # Required default
                    mbti=random.choice(self.MBTI_TYPES),  # Required default
                    country=random.choice(self.COUNTRIES),  # Required default
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Starting parallel generation of {total} Agent personas (parallelism: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"Starting Agent persona generation - {total} total entities, parallelism: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Run in parallel using a thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Submit all tasks
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Write to file in real time
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completed {current}/{total}: {entity.name} ({entity_type})"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} used a fallback persona: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Persona generated successfully: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"An exception occurred while processing entity {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                        age=30,  # Required default
                        gender="other",  # Required default
                        mbti=random.choice(self.MBTI_TYPES),  # Required default
                        country=random.choice(self.COUNTRIES),  # Required default
                    )
                    # Write to file in real time, even for fallback profiles
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"Persona generation complete. Generated {len([p for p in profiles if p])} Agents")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Print the generated persona to the console in real time, without truncation."""
        separator = "-" * 70
        
        # Build the full output content without truncation
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'
        
        output_lines = [
            f"\n{separator}",
            f"[Generated] {entity_name} ({entity_type})",
            f"{separator}",
            f"Username: {profile.user_name}",
            f"",
            f"[Bio]",
            f"{profile.bio}",
            f"",
            f"[Detailed Persona]",
            f"{profile.persona}",
            f"",
            f"[Basic Attributes]",
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}",
            f"Profession: {profile.profession} | Country: {profile.country}",
            f"Interested Topics: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Output only to the console to avoid duplication in logs
        print(output)
    
    @staticmethod
    def _validate_profile_completeness(profiles: List[OasisAgentProfile], platform: str = "unknown") -> tuple[int, List[str]]:
        """
        Validate that all profiles have required fields for OASIS compatibility.

        OASIS requires: age, gender, mbti, country

        Args:
            profiles: List of profiles to validate
            platform: Platform name for logging context

        Returns:
            (error_count, error_messages) - Number of invalid profiles and details
        """
        errors = []
        required_fields = ["age", "gender", "mbti", "country"]

        for idx, profile in enumerate(profiles):
            if not profile:
                errors.append(f"Profile at index {idx} is None")
                continue

            missing_fields = []
            for field in required_fields:
                value = getattr(profile, field, None)
                if value is None or (isinstance(value, str) and not value):
                    missing_fields.append(field)

            if missing_fields:
                errors.append(
                    f"Profile {idx} ({profile.name}): missing required fields {missing_fields}"
                )

        if errors:
            logger.error(f"[{platform}] Profile validation failed - {len(errors)} incomplete profiles detected:")
            for error in errors[:10]:  # Log first 10 errors
                logger.error(f"  - {error}")
            if len(errors) > 10:
                logger.error(f"  ... and {len(errors) - 10} more")

        return len(errors), errors

    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Save profiles to a file using the correct format for the selected platform.

        OASIS platform format requirements:
        - Twitter: CSV format
        - Reddit: JSON format

        Args:
            profiles: List of profiles
            file_path: Output file path
            platform: Platform type ("reddit" or "twitter")
        """
        # Validate profiles before saving
        error_count, error_messages = self._validate_profile_completeness(profiles, platform)
        if error_count > 0:
            logger.warning(
                f"Saving {len(profiles)} profiles with {error_count} incomplete entries. "
                f"These will use OASIS fallback defaults. Consider fixing the profile generator."
            )

        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Twitter Profiles in CSV format, matching official OASIS requirements.
        
        OASIS Twitter CSV fields:
        - user_id: User ID (starts from 0 based on CSV order)
        - name: User's real name
        - username: Username in the system
        - user_char: Detailed persona description (injected into the LLM system prompt to guide Agent behavior)
        - description: Short public bio (displayed on the user profile page)
        
        Difference between user_char and description:
        - user_char: Used internally in the LLM system prompt and determines how the Agent thinks and acts
        - description: Displayed externally as the bio visible to other users
        """
        import csv
        
        # Ensure the file extension is .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write the header required by OASIS
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Write data rows
            for idx, profile in enumerate(profiles):
                # user_char: full persona (bio + persona), used in the LLM system prompt
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Replace newline characters with spaces for CSV output
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: short bio used for external display
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: sequential ID starting from 0
                    profile.name,           # name: real name
                    profile.user_name,      # username: username
                    user_char,              # user_char: full persona (used internally by the LLM)
                    description             # description: short bio (displayed externally)
                ]
                writer.writerow(row)
        
        logger.info(f"Saved {len(profiles)} Twitter Profiles to {file_path} (OASIS CSV format)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Normalize the gender field to the English format required by OASIS.
        
        OASIS requires: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # Chinese and English mappings
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # Existing English keys
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Reddit Profiles in JSON format.
        
        Use the same format as to_reddit_format() so OASIS can read it correctly.
        The user_id field is required because it is the key used by
        OASIS agent_graph.get_agent() for matching.
        
        Required fields:
        - user_id: User ID (integer, used to match poster_agent_id in initial_posts)
        - username: Username
        - name: Display name
        - bio: Bio
        - persona: Detailed persona
        - age: Age (integer)
        - gender: "male", "female", or "other"
        - mbti: MBTI type
        - country: Country
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Use the same format as to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Key requirement: must include user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS required fields - ensure defaults exist
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "China",
            }
            
            # Optional fields
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(profiles)} Reddit Profiles to {file_path} (JSON format, including user_id)")
    
    # Keep the old method name as an alias for backward compatibility
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecated] Please use save_profiles()."""
        logger.warning("save_profiles_to_json is deprecated, please use save_profiles instead")
        self.save_profiles(profiles, file_path, platform)
