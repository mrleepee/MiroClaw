"""Background episode processor: text -> entity extraction -> graph update."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import GraphNode, GraphEdge, Episode, OntologyDefinition, _new_uuid, _now

logger = logging.getLogger(__name__)


class EpisodeProcessor:
    """Processes episodes: extracts entities/relationships via LLM,
    creates/updates nodes and edges in Neo4j, generates embeddings."""

    def __init__(self, neo4j_client, entity_extractor, embedding_service):
        """
        Args:
            neo4j_client: Neo4jClient instance.
            entity_extractor: EntityExtractor instance.
            embedding_service: EmbeddingService instance.
        """
        self._neo4j = neo4j_client
        self._extractor = entity_extractor
        self._embeddings = embedding_service

    def process_episode(
        self,
        episode: Episode,
        ontology: OntologyDefinition,
    ) -> Dict[str, int]:
        """Process a single episode: extract entities/relationships and update graph.

        Args:
            episode: The episode to process.
            ontology: The ontology definition for the graph.

        Returns:
            Dict with counts: {"entities_created": N, "entities_updated": N,
                               "relationships_created": N}
        """
        stats = {"entities_created": 0, "entities_updated": 0, "relationships_created": 0}

        if not episode.data or not episode.data.strip():
            self._mark_processed(episode)
            return stats

        # Get existing entity names for deduplication
        existing_names = self._get_existing_entity_names(episode.graph_id)

        # Extract entities and relationships from text
        ontology_dict = {
            "entity_types": ontology.entity_types,
            "edge_types": ontology.edge_types,
        }
        extraction = self._extractor.extract(
            text=episode.data,
            ontology=ontology_dict,
            existing_entity_names=existing_names,
        )

        # Upsert entities (MERGE by name within graph)
        entity_name_to_uuid = {}
        for entity_data in extraction.get("entities", []):
            node, created = self._upsert_entity(episode.graph_id, entity_data)
            entity_name_to_uuid[node.name.lower()] = node.uuid_
            if created:
                stats["entities_created"] += 1
            else:
                stats["entities_updated"] += 1

        # Create relationships
        for rel_data in extraction.get("relationships", []):
            created = self._create_relationship(
                episode.graph_id, rel_data, entity_name_to_uuid
            )
            if created:
                stats["relationships_created"] += 1

        # Mark episode as processed
        self._mark_processed(episode)

        logger.info(
            f"Processed episode {episode.uuid_}: "
            f"{stats['entities_created']} new entities, "
            f"{stats['entities_updated']} updated, "
            f"{stats['relationships_created']} relationships"
        )
        return stats

    def process_batch(
        self,
        episodes: List[Episode],
        ontology: OntologyDefinition,
    ) -> Dict[str, int]:
        """Process multiple episodes sequentially.

        Returns:
            Aggregated stats.
        """
        totals = {"entities_created": 0, "entities_updated": 0, "relationships_created": 0}
        for episode in episodes:
            try:
                stats = self.process_episode(episode, ontology)
                for k, v in stats.items():
                    totals[k] += v
            except Exception as e:
                logger.error(f"Failed to process episode {episode.uuid_}: {e}")
        return totals

    def _get_existing_entity_names(self, graph_id: str) -> List[str]:
        """Get names of all entities in the graph for deduplication."""
        results = self._neo4j.run_query(
            "MATCH (n:Entity {graph_id: $graph_id}) RETURN n.name AS name",
            {"graph_id": graph_id},
        )
        return [r["name"] for r in results if r.get("name")]

    def _upsert_entity(
        self, graph_id: str, entity_data: Dict[str, Any]
    ) -> tuple[GraphNode, bool]:
        """Create or update an entity node.

        Returns:
            Tuple of (GraphNode, was_created).
        """
        name = entity_data["name"]
        entity_type = entity_data.get("type", "Entity")
        summary = entity_data.get("summary", "")
        attributes = entity_data.get("attributes", {})
        entity_category = entity_data.get("category", "actor")

        # Generate embedding for the entity summary
        embedding = None
        if summary:
            embedding = self._embeddings.encode_single(summary)

        # MERGE by name (case-insensitive) within the same graph
        query = """
        MERGE (n:Entity {graph_id: $graph_id, name_lower: toLower($name)})
        ON CREATE SET
            n.uuid = $uuid,
            n.name = $name,
            n.summary = $summary,
            n.attributes = $attributes,
            n.labels_json = $labels_json,
            n.entity_category = $entity_category,
            n.created_at = $created_at,
            n.embedding = $embedding,
            n:""" + _safe_label(entity_type) + """
        ON MATCH SET
            n.summary = CASE WHEN size(n.summary) < size($summary) THEN $summary ELSE n.summary END,
            n.attributes = $attributes,
            n.entity_category = $entity_category,
            n.embedding = CASE WHEN $embedding IS NOT NULL THEN $embedding ELSE n.embedding END
        RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
               n.labels_json AS labels_json, n.attributes AS attributes,
               n.created_at AS created_at, n.entity_category AS entity_category,
               CASE WHEN n.created_at = $created_at THEN true ELSE false END AS created
        """

        new_uuid = _new_uuid()
        labels = ["Entity", entity_type] if entity_type != "Entity" else ["Entity"]

        results = self._neo4j.run_write(query, {
            "graph_id": graph_id,
            "name": name,
            "uuid": new_uuid,
            "summary": summary,
            "attributes": _serialize_json(attributes),
            "labels_json": _serialize_json(labels),
            "entity_category": entity_category,
            "created_at": _now(),
            "embedding": embedding,
        })

        if results:
            r = results[0]
            node = GraphNode(
                uuid_=r["uuid"],
                name=r["name"],
                summary=r.get("summary", ""),
                labels=_deserialize_json(r.get("labels_json", "[]")),
                attributes=_deserialize_json(r.get("attributes", "{}")),
                created_at=r.get("created_at"),
                graph_id=graph_id,
            )
            return node, r.get("created", False)

        # Fallback: return a new node
        node = GraphNode(
            uuid_=new_uuid, name=name, labels=labels,
            summary=summary, attributes=attributes, graph_id=graph_id,
        )
        return node, True

    def _create_relationship(
        self,
        graph_id: str,
        rel_data: Dict[str, Any],
        entity_name_to_uuid: Dict[str, str],
    ) -> bool:
        """Create a relationship edge between two entities."""
        source_name = rel_data["source"]
        target_name = rel_data["target"]
        rel_type = rel_data.get("type", "RELATED_TO")
        fact = rel_data.get("fact", "")

        # Look up entity UUIDs
        source_uuid = entity_name_to_uuid.get(source_name.lower())
        target_uuid = entity_name_to_uuid.get(target_name.lower())

        if not source_uuid or not target_uuid:
            # Try to find in graph
            if not source_uuid:
                source_uuid = self._find_entity_uuid(graph_id, source_name)
            if not target_uuid:
                target_uuid = self._find_entity_uuid(graph_id, target_name)

        if not source_uuid or not target_uuid:
            logger.debug(
                f"Skipping relationship {source_name} -> {target_name}: "
                f"entity not found"
            )
            return False

        # Generate embedding for the fact
        embedding = self._embeddings.encode_single(fact) if fact else None

        query = """
        MATCH (source:Entity {uuid: $source_uuid})
        MATCH (target:Entity {uuid: $target_uuid})
        CREATE (source)-[r:RELATIONSHIP {
            uuid: $uuid,
            name: $name,
            fact: $fact,
            graph_id: $graph_id,
            created_at: $created_at,
            valid_at: $valid_at,
            embedding: $embedding
        }]->(target)
        RETURN r.uuid AS uuid
        """

        now = _now()
        results = self._neo4j.run_write(query, {
            "source_uuid": source_uuid,
            "target_uuid": target_uuid,
            "uuid": _new_uuid(),
            "name": rel_type,
            "fact": fact,
            "graph_id": graph_id,
            "created_at": now,
            "valid_at": now,
            "embedding": embedding,
        })

        return len(results) > 0

    def _find_entity_uuid(self, graph_id: str, name: str) -> Optional[str]:
        """Find entity UUID by name (case-insensitive)."""
        results = self._neo4j.run_query(
            "MATCH (n:Entity {graph_id: $graph_id, name_lower: toLower($name)}) "
            "RETURN n.uuid AS uuid LIMIT 1",
            {"graph_id": graph_id, "name": name},
        )
        return results[0]["uuid"] if results else None

    def _mark_processed(self, episode: Episode):
        """Mark an episode as processed in Neo4j."""
        self._neo4j.run_write(
            "MATCH (e:Episode {uuid: $uuid}) SET e.processed = true",
            {"uuid": episode.uuid_},
        )
        episode.processed = True


def _safe_label(label: str) -> str:
    """Sanitize a label for use in Cypher (alphanumeric + underscore only)."""
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", label)
    return cleaned if cleaned else "Entity"


def _serialize_json(obj) -> str:
    """Serialize to JSON string for Neo4j storage."""
    import json
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def _deserialize_json(s) -> Any:
    """Deserialize from JSON string."""
    import json
    if not s:
        return {}
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}
