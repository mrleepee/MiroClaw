"""
Graph building service
Builds knowledge graphs using LocalGraphService (Neo4j + LLM)
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .local_graph import LocalGraphService, EpisodeData
from .local_graph.graph_service import Neo4jClient
from .local_graph.entity_extractor import EntityExtractor
from .local_graph.embedding_service import EmbeddingService
from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger('miroclaw.graph_builder')


@dataclass
class GraphInfo:
    """Graph information"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


# Singleton LocalGraphService instance
_graph_service_instance: Optional[LocalGraphService] = None
_graph_service_lock = threading.Lock()


def get_graph_service() -> LocalGraphService:
    """Get or create the singleton LocalGraphService instance."""
    global _graph_service_instance

    if _graph_service_instance is None:
        with _graph_service_lock:
            if _graph_service_instance is None:
                # Initialize Neo4j client
                neo4j_client = Neo4jClient(
                    uri=Config.NEO4J_URI,
                    user=Config.NEO4J_USER,
                    password=Config.NEO4J_PASSWORD
                )

                # Initialize LLM client for entity extraction
                from ..utils.llm_client import LLMClient
                llm_client = LLMClient()

                # Initialize entity extractor
                entity_extractor = EntityExtractor(llm_client)

                # Initialize embedding service
                embedding_service = EmbeddingService(
                    model_name=Config.EMBEDDING_MODEL_NAME
                )

                # Create the graph service
                _graph_service_instance = LocalGraphService(
                    neo4j_client=neo4j_client,
                    entity_extractor=entity_extractor,
                    embedding_service=embedding_service
                )

                # Initialize indexes
                try:
                    _graph_service_instance.initialize()
                    logger.info("LocalGraphService initialized successfully")
                except Exception as e:
                    logger.warning(f"LocalGraphService initialization warning: {e}")

    return _graph_service_instance


class GraphBuilderService:
    """
    Graph building service
    Builds knowledge graphs using LocalGraphService
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key parameter kept for backward compatibility but not used
        self.graph_service = get_graph_service()
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroClaw Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Build graph asynchronously

        Args:
            text: Input text
            ontology: Ontology definition
            graph_name: Graph name
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            batch_size: Number of chunks to send per batch

        Returns:
            Task ID
        """
        # Create task
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        # Run the build in a background thread
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """Graph building worker thread"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting graph build..."
            )

            # 1. Create graph
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )

            # 2. Set ontology
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontology set"
            )

            # 3. Split text into chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )

            # 4. Send data in batches (LocalGraphService processes immediately)
            self.task_manager.update_task(
                task_id,
                progress=25,
                message="Processing text chunks with LLM..."
            )

            self._add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=25 + int(prog * 0.65),  # 25-90%
                    message=msg
                )
            )

            # 5. Get graph information
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="Getting graph information..."
            )

            graph_info = self._get_graph_info(graph_id)

            # Complete
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """Create a new graph"""
        graph_id = f"miroclaw_{uuid.uuid4().hex[:16]}"

        self.graph_service.create(
            graph_id=graph_id,
            name=name,
            description="MiroClaw Social Simulation Graph"
        )

        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """Set graph ontology, preserving actor/context classification."""
        # Convert ontology format for LocalGraphService
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            entity_types[name] = {
                "description": entity_def.get("description", f"A {name} entity."),
                "attributes": entity_def.get("attributes", []),
                "base_type": entity_def.get("base_type", ""),
                "category": entity_def.get("category", "actor"),
            }

        edge_types = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            edge_types[name] = {
                "description": edge_def.get("description", f"A {name} relationship."),
                "attributes": edge_def.get("attributes", []),
                "source_targets": edge_def.get("source_targets", [])
            }

        self.graph_service.set_ontology(
            graph_ids=[graph_id],
            entities=entity_types,
            edges=edge_types
        )

    def _add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ):
        """Add text to the graph in batches"""
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)...",
                    progress
                )

            # Build episode data
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]

            # Send to LocalGraphService (processes immediately via LLM)
            try:
                self.graph_service.add_batch(graph_id, episodes)

                # Small delay to avoid overwhelming the LLM
                time.sleep(0.5)

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Failed to process batch {batch_num}: {str(e)}", 0)
                raise

        if progress_callback:
            progress_callback(f"Processed all {total_chunks} chunks", 1.0)

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Get graph information"""
        # Fetch nodes
        nodes = self.graph_service.node.get_by_graph_id(graph_id, limit=10000)

        # Fetch edges
        edges = self.graph_service.edge.get_by_graph_id(graph_id, limit=10000)

        # Count entity types
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Get complete graph data

        Args:
            graph_id: Graph ID

        Returns:
            Dictionary containing nodes and edges
        """
        nodes = self.graph_service.node.get_by_graph_id(graph_id, limit=10000)
        edges = self.graph_service.edge.get_by_graph_id(graph_id, limit=10000)

        # Create a node mapping for looking up node names
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": node.created_at,
            })

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": edge.name or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": edge.created_at,
                "valid_at": edge.valid_at,
                "invalid_at": edge.invalid_at,
                "expired_at": edge.expired_at,
                "episodes": [],
            })

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Delete graph"""
        self.graph_service.delete(graph_id)
