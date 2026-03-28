"""Neo4j connection management and Cypher query helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, Driver, Session

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Manages Neo4j driver lifecycle and provides query helpers."""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver: Optional[Driver] = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password),
                connection_timeout=10,  # Fail fast when Neo4j is down
                max_transaction_retry_time=15,  # Don't retry for 60s
            )
        return self._driver

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def verify_connectivity(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    def session(self) -> Session:
        return self.driver.session(database=self._database)

    def run_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts."""
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_write(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a write transaction."""
        with self.session() as session:

            def _work(tx):
                result = tx.run(query, parameters or {})
                return [record.data() for record in result]

            return session.execute_write(lambda tx: _work(tx))

    def ensure_indexes(self):
        """Create constraints and indexes if they don't exist."""
        index_queries = [
            # Uniqueness constraints
            "CREATE CONSTRAINT graph_id IF NOT EXISTS FOR (g:Graph) REQUIRE g.id IS UNIQUE",
            "CREATE CONSTRAINT node_uuid IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS UNIQUE",
            "CREATE CONSTRAINT episode_uuid IF NOT EXISTS FOR (e:Episode) REQUIRE e.uuid IS UNIQUE",
            # Lookup indexes
            "CREATE INDEX entity_graph_id IF NOT EXISTS FOR (n:Entity) ON (n.graph_id)",
            "CREATE INDEX episode_graph_id IF NOT EXISTS FOR (e:Episode) ON (e.graph_id)",
            "CREATE INDEX episode_processed IF NOT EXISTS FOR (e:Episode) ON (e.processed)",
            # Composite index for entity MERGE pattern {graph_id, name_lower}
            "CREATE INDEX entity_graph_name IF NOT EXISTS FOR (n:Entity) ON (n.graph_id, n.name_lower)",
            # Relationship index — every edge query filters by graph_id
            "CREATE INDEX relationship_graph_id IF NOT EXISTS FOR ()-[r:RELATIONSHIP]-() ON (r.graph_id)",
            # Full-text indexes for keyword search
            "CREATE FULLTEXT INDEX entity_text_search IF NOT EXISTS FOR (n:Entity) ON EACH [n.name, n.summary]",
            "CREATE FULLTEXT INDEX relationship_fact_text IF NOT EXISTS FOR ()-[r:RELATIONSHIP]-() ON EACH [r.fact, r.name]",
        ]
        for query in index_queries:
            try:
                self.run_write(query)
            except Exception as e:
                # Index may already exist
                logger.debug(f"Index creation note: {e}")

    def ensure_vector_indexes(self, dimensions: int = 1024):
        """Create vector indexes for semantic search.

        Args:
            dimensions: Embedding vector dimensions (Qwen3-Embedding-4B = 1024 by default).
        """
        vector_queries = [
            f"""CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
                FOR (n:Entity) ON (n.embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {dimensions},
                    `vector.similarity_function`: 'cosine'
                }}}}""",
        ]
        for query in vector_queries:
            try:
                self.run_write(query)
            except Exception as e:
                logger.debug(f"Vector index creation note: {e}")

    def clear_graph(self, graph_id: str):
        """Delete all nodes and relationships for a graph."""
        queries = [
            "MATCH (e:Episode {graph_id: $graph_id}) DETACH DELETE e",
            "MATCH (n:Entity {graph_id: $graph_id}) DETACH DELETE n",
            "MATCH (o:Ontology {graph_id: $graph_id}) DETACH DELETE o",
            "MATCH (g:Graph {id: $graph_id}) DETACH DELETE g",
        ]
        for query in queries:
            self.run_write(query, {"graph_id": graph_id})
