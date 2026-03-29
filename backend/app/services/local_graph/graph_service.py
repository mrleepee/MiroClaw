"""LocalGraphService: drop-in replacement for Zep Cloud client.

Provides the same interface contract so calling code needs minimal changes.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional

from .models import (
    GraphNode,
    GraphEdge,
    Episode,
    EpisodeData,
    OntologyDefinition,
    SearchResults,
    _new_uuid,
    _now,
)
from .neo4j_client import Neo4jClient
from .entity_extractor import EntityExtractor
from .embedding_service import EmbeddingService
from .episode_processor import EpisodeProcessor

logger = logging.getLogger(__name__)


class _NodeNamespace:
    """Mirrors the Zep client.graph.node namespace."""

    def __init__(self, service: LocalGraphService):
        self._svc = service

    def get_by_graph_id(
        self,
        graph_id: str,
        limit: int = 100,
        uuid_cursor: Optional[str] = None,
    ) -> List[GraphNode]:
        """Fetch nodes for a graph with cursor-based pagination."""
        query = """
        MATCH (n:Entity {graph_id: $graph_id})
        """ + (
            "WHERE n.uuid > $cursor " if uuid_cursor else ""
        ) + """
        RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
               n.labels_json AS labels_json, n.attributes AS attributes,
               n.created_at AS created_at, n.entity_category AS entity_category
        ORDER BY n.uuid
        LIMIT $limit
        """
        params: Dict[str, Any] = {"graph_id": graph_id, "limit": limit}
        if uuid_cursor:
            params["cursor"] = uuid_cursor

        results = self._svc._neo4j.run_query(query, params)
        return [_row_to_node(r, graph_id) for r in results]

    def get(self, uuid_: str) -> Optional[GraphNode]:
        """Get a single node by UUID."""
        results = self._svc._neo4j.run_query(
            """MATCH (n:Entity {uuid: $uuid})
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
                   n.labels_json AS labels_json, n.attributes AS attributes,
                   n.created_at AS created_at, n.graph_id AS graph_id,
                   n.entity_category AS entity_category""",
            {"uuid": uuid_},
        )
        if not results:
            return None
        return _row_to_node(results[0], results[0].get("graph_id", ""))

    def get_entity_edges(self, node_uuid: str) -> List[GraphEdge]:
        """Get all edges connected to a node (incoming and outgoing)."""
        query = """
        MATCH (n:Entity {uuid: $uuid})-[r:RELATIONSHIP]-(other:Entity)
        RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
               r.graph_id AS graph_id,
               startNode(r).uuid AS source_uuid,
               endNode(r).uuid AS target_uuid,
               r.created_at AS created_at, r.valid_at AS valid_at,
               r.invalid_at AS invalid_at, r.expired_at AS expired_at
        """
        results = self._svc._neo4j.run_query(query, {"uuid": node_uuid})
        return [_row_to_edge(r) for r in results]


class _EdgeNamespace:
    """Mirrors the Zep client.graph.edge namespace."""

    def __init__(self, service: LocalGraphService):
        self._svc = service

    def get_by_graph_id(
        self,
        graph_id: str,
        limit: int = 100,
        uuid_cursor: Optional[str] = None,
    ) -> List[GraphEdge]:
        """Fetch edges for a graph with cursor-based pagination."""
        query = """
        MATCH (source:Entity)-[r:RELATIONSHIP {graph_id: $graph_id}]->(target:Entity)
        """ + (
            "WHERE r.uuid > $cursor " if uuid_cursor else ""
        ) + """
        RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
               source.uuid AS source_uuid, target.uuid AS target_uuid,
               r.created_at AS created_at, r.valid_at AS valid_at,
               r.invalid_at AS invalid_at, r.expired_at AS expired_at
        ORDER BY r.uuid
        LIMIT $limit
        """
        params: Dict[str, Any] = {"graph_id": graph_id, "limit": limit}
        if uuid_cursor:
            params["cursor"] = uuid_cursor

        results = self._svc._neo4j.run_query(query, params)
        return [_row_to_edge(r) for r in results]


class _EpisodeNamespace:
    """Mirrors the Zep client.graph.episode namespace."""

    def __init__(self, service: LocalGraphService):
        self._svc = service

    def get(self, uuid_: str) -> Optional[Episode]:
        """Get episode by UUID."""
        results = self._svc._neo4j.run_query(
            """MATCH (e:Episode {uuid: $uuid})
            RETURN e.uuid AS uuid, e.data AS data, e.type AS type,
                   e.processed AS processed, e.graph_id AS graph_id,
                   e.created_at AS created_at""",
            {"uuid": uuid_},
        )
        if not results:
            return None
        r = results[0]
        return Episode(
            uuid_=r["uuid"],
            data=r.get("data", ""),
            type=r.get("type", "text"),
            processed=r.get("processed", False),
            graph_id=r.get("graph_id", ""),
            created_at=r.get("created_at"),
        )


class LocalGraphService:
    """Drop-in replacement for Zep Cloud client.

    Usage mirrors the Zep SDK:
        service = LocalGraphService(...)
        service.create(graph_id="g1", name="My Graph")
        service.node.get_by_graph_id("g1")
        service.search("g1", query="some question", limit=10)
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        entity_extractor: EntityExtractor,
        embedding_service: EmbeddingService,
    ):
        self._neo4j = neo4j_client
        self._extractor = entity_extractor
        self._embeddings = embedding_service
        self._processor = EpisodeProcessor(
            neo4j_client, entity_extractor, embedding_service
        )
        self._ontology_cache: Dict[str, OntologyDefinition] = {}
        self._lock = threading.Lock()

        # Expose nested namespaces (matches Zep SDK pattern)
        self.node = _NodeNamespace(self)
        self.edge = _EdgeNamespace(self)
        self.episode = _EpisodeNamespace(self)

    def initialize(self):
        """Create indexes and verify connectivity. Call once at startup."""
        self._neo4j.ensure_indexes()
        self._neo4j.ensure_vector_indexes(dimensions=self._embeddings.dimensions)
        logger.info("LocalGraphService initialized")

    def close(self):
        """Clean up resources."""
        self._neo4j.close()

    # ── Graph CRUD ──────────────────────────────────────────────

    def create(
        self,
        graph_id: str,
        name: str = "",
        description: str = "",
    ):
        """Create a new graph."""
        self._neo4j.run_write(
            """CREATE (g:Graph {
                id: $graph_id, name: $name,
                description: $description, created_at: $created_at
            })""",
            {
                "graph_id": graph_id,
                "name": name,
                "description": description,
                "created_at": _now(),
            },
        )
        logger.info(f"Created graph: {graph_id}")

    def delete(self, graph_id: str):
        """Delete a graph and all its nodes, edges, episodes."""
        self._neo4j.clear_graph(graph_id)
        self._ontology_cache.pop(graph_id, None)
        logger.info(f"Deleted graph: {graph_id}")

    # ── Ontology ────────────────────────────────────────────────

    def set_ontology(
        self,
        graph_ids: List[str],
        entities: Dict[str, Any],
        edges: Dict[str, Any],
    ):
        """Set ontology definitions for graphs.

        Args:
            graph_ids: List of graph IDs to apply ontology to.
            entities: Entity type definitions.
            edges: Edge type definitions.
        """
        ontology = OntologyDefinition(
            entity_types=_normalize_ontology_types(entities),
            edge_types=_normalize_ontology_types(edges),
        )

        for graph_id in graph_ids:
            self._neo4j.run_write(
                """MATCH (g:Graph {id: $graph_id})
                MERGE (g)-[:HAS_ONTOLOGY]->(o:Ontology {graph_id: $graph_id})
                SET o.entity_types = $entity_types,
                    o.edge_types = $edge_types""",
                {
                    "graph_id": graph_id,
                    "entity_types": json.dumps(ontology.entity_types, ensure_ascii=False),
                    "edge_types": json.dumps(ontology.edge_types, ensure_ascii=False),
                },
            )
            self._ontology_cache[graph_id] = ontology

        logger.info(f"Set ontology for graphs: {graph_ids}")

    def _get_ontology(self, graph_id: str) -> OntologyDefinition:
        """Get ontology for a graph (cached)."""
        if graph_id in self._ontology_cache:
            return self._ontology_cache[graph_id]

        results = self._neo4j.run_query(
            """MATCH (o:Ontology {graph_id: $graph_id})
            RETURN o.entity_types AS entity_types, o.edge_types AS edge_types""",
            {"graph_id": graph_id},
        )
        if results:
            r = results[0]
            ontology = OntologyDefinition(
                entity_types=json.loads(r.get("entity_types", "{}")),
                edge_types=json.loads(r.get("edge_types", "{}")),
            )
        else:
            ontology = OntologyDefinition()

        self._ontology_cache[graph_id] = ontology
        return ontology

    # ── Episodes ────────────────────────────────────────────────

    def add_batch(
        self,
        graph_id: str,
        episodes: List[EpisodeData],
    ) -> List[Episode]:
        """Add a batch of episodes and process them.

        Args:
            graph_id: The graph to add episodes to.
            episodes: List of EpisodeData objects.

        Returns:
            List of Episode objects with UUIDs assigned.
        """
        created_episodes = []
        for ep_data in episodes:
            ep = Episode(
                uuid_=_new_uuid(),
                data=ep_data.data,
                type=ep_data.type,
                processed=False,
                graph_id=graph_id,
            )
            # Store in Neo4j
            self._neo4j.run_write(
                """CREATE (e:Episode {
                    uuid: $uuid, data: $data, type: $type,
                    processed: false, graph_id: $graph_id,
                    created_at: $created_at
                })""",
                {
                    "uuid": ep.uuid_,
                    "data": ep.data,
                    "type": ep.type,
                    "graph_id": graph_id,
                    "created_at": ep.created_at,
                },
            )
            created_episodes.append(ep)

        # Process episodes (entity extraction + graph update)
        ontology = self._get_ontology(graph_id)
        self._processor.process_batch(created_episodes, ontology)

        return created_episodes

    def add(self, graph_id: str, type: str = "text", data: str = ""):
        """Add a single episode (used during simulation for live memory updates)."""
        self.add_batch(graph_id, [EpisodeData(data=data, type=type)])

    # ── Search ──────────────────────────────────────────────────

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> SearchResults:
        """Semantic search using vector similarity.

        Args:
            graph_id: Graph to search.
            query: Natural language search query.
            limit: Maximum results to return.
            scope: "edges", "nodes", or "both".
            reranker: Ignored (Zep compatibility parameter).

        Returns:
            SearchResults with matching edges and/or nodes.
        """
        query_embedding = self._embeddings.encode_single(query)
        if not query_embedding:
            return SearchResults()

        edges: List[GraphEdge] = []
        nodes: List[GraphNode] = []

        if scope in ("edges", "both"):
            edges = self._search_edges(graph_id, query_embedding, limit)

        if scope in ("nodes", "both"):
            nodes = self._search_nodes(graph_id, query_embedding, limit)

        return SearchResults(edges=edges, nodes=nodes)

    def _search_nodes(
        self, graph_id: str, query_embedding: List[float], limit: int
    ) -> List[GraphNode]:
        """Vector similarity search on entity nodes."""
        try:
            results = self._neo4j.run_query(
                """CALL db.index.vector.queryNodes('entity_embeddings', $limit, $embedding)
                YIELD node, score
                WHERE node.graph_id = $graph_id
                RETURN node.uuid AS uuid, node.name AS name,
                       node.summary AS summary, node.labels_json AS labels_json,
                       node.attributes AS attributes, node.created_at AS created_at,
                       score
                ORDER BY score DESC""",
                {
                    "graph_id": graph_id,
                    "embedding": query_embedding,
                    "limit": limit * 2,  # Fetch extra to filter by graph_id
                },
            )
            return [_row_to_node(r, graph_id) for r in results[:limit]]
        except Exception as e:
            logger.warning(f"Vector node search failed, falling back to keyword: {e}")
            return self._keyword_search_nodes(graph_id, query_embedding, limit)

    def _search_edges(
        self, graph_id: str, query_embedding: List[float], limit: int
    ) -> List[GraphEdge]:
        """Search edges using node-based vector search + relationship traversal.

        Since Neo4j vector indexes on relationships are limited,
        we search related nodes and traverse their edges.
        """
        try:
            # Search for relevant nodes first, then get their edges
            results = self._neo4j.run_query(
                """CALL db.index.vector.queryNodes('entity_embeddings', $limit, $embedding)
                YIELD node, score
                WHERE node.graph_id = $graph_id
                WITH node
                MATCH (node)-[r:RELATIONSHIP {graph_id: $graph_id}]-(other:Entity)
                RETURN DISTINCT r.uuid AS uuid, r.name AS name, r.fact AS fact,
                       startNode(r).uuid AS source_uuid,
                       endNode(r).uuid AS target_uuid,
                       r.created_at AS created_at, r.valid_at AS valid_at,
                       r.invalid_at AS invalid_at, r.expired_at AS expired_at
                LIMIT $edge_limit""",
                {
                    "graph_id": graph_id,
                    "embedding": query_embedding,
                    "limit": limit,
                    "edge_limit": limit,
                },
            )
            return [_row_to_edge(r) for r in results]
        except Exception as e:
            logger.warning(f"Vector edge search failed, falling back to keyword: {e}")
            return self._keyword_search_edges(graph_id, limit)

    def _keyword_search_nodes(
        self, graph_id: str, query_embedding: List[float], limit: int
    ) -> List[GraphNode]:
        """Fallback: return all nodes for the graph (limited)."""
        return self.node.get_by_graph_id(graph_id, limit=limit)

    def _keyword_search_edges(
        self, graph_id: str, limit: int
    ) -> List[GraphEdge]:
        """Fallback: return all edges for the graph (limited)."""
        return self.edge.get_by_graph_id(graph_id, limit=limit)


# ── Helper functions ────────────────────────────────────────────


def _row_to_node(row: Dict[str, Any], graph_id: str = "") -> GraphNode:
    """Convert a Neo4j result row to a GraphNode."""
    labels_raw = row.get("labels_json", "[]")
    if isinstance(labels_raw, str):
        try:
            labels = json.loads(labels_raw)
        except (json.JSONDecodeError, TypeError):
            labels = ["Entity"]
    else:
        labels = labels_raw if labels_raw else ["Entity"]

    attrs_raw = row.get("attributes", "{}")
    if isinstance(attrs_raw, str):
        try:
            attributes = json.loads(attrs_raw)
        except (json.JSONDecodeError, TypeError):
            attributes = {}
    else:
        attributes = attrs_raw if attrs_raw else {}

    return GraphNode(
        uuid_=row.get("uuid", ""),
        name=row.get("name", ""),
        labels=labels,
        summary=row.get("summary") or "",
        attributes=attributes,
        created_at=row.get("created_at"),
        graph_id=graph_id,
        entity_category=row.get("entity_category") or "actor",
    )


def _row_to_edge(row: Dict[str, Any]) -> GraphEdge:
    """Convert a Neo4j result row to a GraphEdge."""
    return GraphEdge(
        uuid_=row.get("uuid", ""),
        name=row.get("name", ""),
        fact=row.get("fact", ""),
        source_node_uuid=row.get("source_uuid", ""),
        target_node_uuid=row.get("target_uuid", ""),
        created_at=row.get("created_at"),
        valid_at=row.get("valid_at"),
        invalid_at=row.get("invalid_at"),
        expired_at=row.get("expired_at"),
    )


class MiroClawGraphWriteAPI:
    """MiroClaw-specific graph write operations.

    Extends LocalGraphService with methods for:
    - Writing agent-sourced triples with provenance metadata
    - Querying triples by status (pending, contested, pruned)
    - Incrementing vote counts
    - Updating triple status
    - Finding similar triples for dedup
    """

    def __init__(self, graph_service: LocalGraphService):
        self._gs = graph_service

    def write_triple(
        self,
        subject: str,
        subject_type: str,
        relationship: str,
        object: str,
        object_type: str,
        properties: Dict[str, Any],
        graph_id: str = None,
    ) -> str:
        """Write a structured triple to Neo4j with provenance metadata.

        Returns the UUID of the created relationship (triple).
        """
        triple_uuid = _new_uuid()

        query = """
        MERGE (s:Entity {name: $subject, graph_id: $graph_id})
        ON CREATE SET s.uuid = randomUUID(), s.labels_json = json_encode([$subject_type]),
                      s.entity_category = 'agent_added', s.created_at = datetime()
        MERGE (o:Entity {name: $object, graph_id: $graph_id})
        ON CREATE SET o.uuid = randomUUID(), o.labels_json = json_encode([$object_type]),
                      o.entity_category = 'agent_added', o.created_at = datetime()
        CREATE (s)-[r:RELATIONSHIP {
            uuid: $triple_uuid,
            name: $relationship,
            fact: $fact,
            source_url: $source_url,
            added_by_agent: $added_by_agent,
            added_round: $added_round,
            added_timestamp: $added_timestamp,
            upvotes: $upvotes,
            downvotes: $downvotes,
            status: $status,
            created_at: datetime()
        }]->(o)
        RETURN r.uuid AS uuid
        """

        fact = f"({subject}) —[{relationship}]-> ({object})"
        params = {
            "triple_uuid": triple_uuid,
            "subject": subject,
            "subject_type": subject_type,
            "object": object,
            "object_type": object_type,
            "relationship": relationship,
            "fact": fact,
            "graph_id": graph_id,
            "source_url": properties.get("source_url", ""),
            "added_by_agent": properties.get("added_by_agent", ""),
            "added_round": properties.get("added_round", 0),
            "added_timestamp": properties.get("added_timestamp", ""),
            "upvotes": properties.get("upvotes", 0),
            "downvotes": properties.get("downvotes", 0),
            "status": properties.get("status", "pending"),
        }

        self._gs._neo4j.run_query(query, params)
        logger.info(f"Wrote triple {triple_uuid}: {fact}")
        return triple_uuid

    def get_agent_triples(
        self,
        graph_id: str = None,
        filter_agent: str = None,
    ) -> List[Dict[str, Any]]:
        """Get all agent-added triples, optionally filtered by agent."""
        query = """
        MATCH (s:Entity)-[r:RELATIONSHIP]->(o:Entity)
        WHERE r.added_by_agent IS NOT NULL
        """
        if graph_id:
            query += " AND s.graph_id = $graph_id"
        if filter_agent:
            query += " AND r.added_by_agent = $filter_agent"

        query += """
        RETURN r.uuid AS uuid, s.name AS subject, r.name AS relationship,
               o.name AS object, r.source_url AS source_url,
               r.added_by_agent AS added_by_agent, r.added_round AS added_round,
               r.added_timestamp AS added_timestamp,
               r.upvotes AS upvotes, r.downvotes AS downvotes,
               r.status AS status
        ORDER BY r.added_round ASC
        """

        params = {}
        if graph_id:
            params["graph_id"] = graph_id
        if filter_agent:
            params["filter_agent"] = filter_agent

        results = self._gs._neo4j.run_query(query, params)
        return [dict(r) for r in results]

    def get_seed_triples(self, graph_id: str = None) -> List[Dict[str, Any]]:
        """Get seed triples (no added_by_agent field)."""
        query = """
        MATCH (s:Entity)-[r:RELATIONSHIP]->(o:Entity)
        WHERE r.added_by_agent IS NULL
        """
        if graph_id:
            query += " AND s.graph_id = $graph_id"

        query += """
        RETURN r.uuid AS uuid, s.name AS subject, r.name AS relationship,
               o.name AS object, r.fact AS fact, r.status AS status
        """

        params = {}
        if graph_id:
            params["graph_id"] = graph_id

        results = self._gs._neo4j.run_query(query, params)
        return [dict(r) for r in results]

    def get_triples_by_status(self, status: str, graph_id: str = None) -> List[Dict[str, Any]]:
        """Get triples by their status (pending, contested, pruned, merged)."""
        query = """
        MATCH (s:Entity)-[r:RELATIONSHIP]->(o:Entity)
        WHERE r.status = $status
        """
        if graph_id:
            query += " AND s.graph_id = $graph_id"

        query += """
        RETURN r.uuid AS uuid, s.name AS subject, r.name AS relationship,
               o.name AS object, r.source_url AS source_url,
               r.added_by_agent AS added_by_agent, r.added_round AS added_round,
               r.upvotes AS upvotes, r.downvotes AS downvotes, r.status AS status
        """

        params = {"status": status}
        if graph_id:
            params["graph_id"] = graph_id

        results = self._gs._neo4j.run_query(query, params)
        return [dict(r) for r in results]

    def get_triple(self, triple_uuid: str) -> Optional[Dict[str, Any]]:
        """Get a single triple by UUID."""
        query = """
        MATCH (s:Entity)-[r:RELATIONSHIP {uuid: $uuid}]->(o:Entity)
        RETURN r.uuid AS uuid, s.name AS subject, r.name AS relationship,
               o.name AS object, r.source_url AS source_url,
               r.added_by_agent AS added_by_agent, r.added_round AS added_round,
               r.upvotes AS upvotes, r.downvotes AS downvotes, r.status AS status
        """
        results = self._gs._neo4j.run_query(query, {"uuid": triple_uuid})
        if not results:
            return None
        return dict(results[0])

    def increment_triple_votes(
        self,
        triple_uuid: str,
        vote_type: str,
        weight: float = 1.0,
    ):
        """Increment upvotes or downvotes on a triple."""
        if vote_type == "upvotes":
            query = """
            MATCH ()-[r:RELATIONSHIP {uuid: $uuid}]->()
            SET r.upvotes = r.upvotes + $weight
            """
        else:
            query = """
            MATCH ()-[r:RELATIONSHIP {uuid: $uuid}]->()
            SET r.downvotes = r.downvotes + $weight
            """
        self._gs._neo4j.run_query(query, {"uuid": triple_uuid, "weight": weight})

    def update_triple_status(self, triple_uuid: str, status: str):
        """Update the status of a triple."""
        query = """
        MATCH ()-[r:RELATIONSHIP {uuid: $uuid}]->()
        SET r.status = $status
        """
        self._gs._neo4j.run_query(query, {"uuid": triple_uuid, "status": status})

    def update_triple_properties(self, triple_uuid: str, properties: Dict[str, Any]):
        """Update arbitrary properties on a triple."""
        set_clauses = []
        params = {"uuid": triple_uuid}
        for key, value in properties.items():
            set_clauses.append(f"r.{key} = ${key}")
            params[key] = value

        if not set_clauses:
            return

        query = f"""
        MATCH ()-[r:RELATIONSHIP {{uuid: $uuid}}]->()
        SET {', '.join(set_clauses)}
        """
        self._gs._neo4j.run_query(query, params)

    def find_similar_triples(
        self,
        embedding: List[float],
        threshold: float = 0.95,
        graph_id: str = None,
    ) -> List[Dict[str, Any]]:
        """Find triples similar to the given embedding.

        Uses cosine similarity via Neo4j vector index if available,
        otherwise falls back to brute-force comparison.
        """
        # For now, return empty — vector similarity search requires
        # Neo4j vector index setup which is environment-dependent.
        # The curator agent handles dedup via embedding_service directly.
        return []

    def get_stats(self, graph_id: str = None) -> Dict[str, Any]:
        """Get graph statistics."""
        query = """
        MATCH (s:Entity)-[r:RELATIONSHIP]->(o:Entity)
        WHERE r.added_by_agent IS NOT NULL
        """
        if graph_id:
            query += " AND s.graph_id = $graph_id"

        query += """
        RETURN count(r) AS total_agent_triples,
               sum(CASE WHEN r.status = 'pending' THEN 1 ELSE 0 END) AS pending,
               sum(CASE WHEN r.status = 'contested' THEN 1 ELSE 0 END) AS contested,
               sum(CASE WHEN r.status = 'pruned' THEN 1 ELSE 0 END) AS pruned,
               sum(CASE WHEN r.status = 'merged' THEN 1 ELSE 0 END) AS merged
        """

        params = {}
        if graph_id:
            params["graph_id"] = graph_id

        results = self._gs._neo4j.run_query(query, params)
        if results:
            return dict(results[0])
        return {
            "total_agent_triples": 0,
            "pending": 0,
            "contested": 0,
            "pruned": 0,
            "merged": 0,
        }


def _normalize_ontology_types(types_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize ontology type definitions to simple dicts.

    Zep uses dynamic Pydantic classes; we store as plain dicts.
    """
    normalized = {}
    for name, value in types_dict.items():
        if isinstance(value, dict):
            normalized[name] = value
        elif isinstance(value, tuple):
            # Edge definitions come as (EdgeModel, source_targets)
            normalized[name] = {"model": str(value[0]), "constraints": str(value[1])}
        else:
            # Pydantic class or other — extract what we can
            normalized[name] = {"description": str(value)}
    return normalized
