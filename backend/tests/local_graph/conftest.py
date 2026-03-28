"""Shared fixtures for local_graph tests."""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.local_graph.models import (
    GraphNode,
    GraphEdge,
    Episode,
    EpisodeData,
    OntologyDefinition,
    SearchResults,
)
from app.services.local_graph.neo4j_client import Neo4jClient
from app.services.local_graph.entity_extractor import EntityExtractor
from app.services.local_graph.embedding_service import EmbeddingService
from app.services.local_graph.episode_processor import EpisodeProcessor
from app.services.local_graph.graph_service import LocalGraphService


# ── Sample Data ─────────────────────────────────────────────────


SAMPLE_ONTOLOGY = OntologyDefinition(
    entity_types={
        "Person": {
            "description": "A person involved in the scenario",
            "attributes": {"role": "Their role or occupation"},
        },
        "Organization": {
            "description": "A company, institution, or group",
            "attributes": {"sector": "Industry sector"},
        },
    },
    edge_types={
        "WORKS_AT": {
            "description": "Employment relationship",
        },
        "COLLABORATES_WITH": {
            "description": "Collaboration between entities",
        },
    },
)

SAMPLE_ONTOLOGY_DICT = {
    "entity_types": SAMPLE_ONTOLOGY.entity_types,
    "edge_types": SAMPLE_ONTOLOGY.edge_types,
}

SAMPLE_TEXT = (
    "Dr. Alice Chen is a senior researcher at TechCorp, a leading AI company. "
    "She collaborates with Bob Wang, a professor at State University. "
    "Together they are working on a joint project for natural language processing."
)

SAMPLE_EXTRACTION_RESULT = {
    "entities": [
        {
            "name": "Alice Chen",
            "type": "Person",
            "summary": "Senior researcher at TechCorp working on NLP",
            "attributes": {"role": "Senior Researcher"},
        },
        {
            "name": "Bob Wang",
            "type": "Person",
            "summary": "Professor at State University collaborating on NLP",
            "attributes": {"role": "Professor"},
        },
        {
            "name": "TechCorp",
            "type": "Organization",
            "summary": "Leading AI company",
            "attributes": {"sector": "Technology"},
        },
        {
            "name": "State University",
            "type": "Organization",
            "summary": "Academic institution",
            "attributes": {"sector": "Education"},
        },
    ],
    "relationships": [
        {
            "source": "Alice Chen",
            "target": "TechCorp",
            "type": "WORKS_AT",
            "fact": "Alice Chen is a senior researcher at TechCorp",
        },
        {
            "source": "Alice Chen",
            "target": "Bob Wang",
            "type": "COLLABORATES_WITH",
            "fact": "Alice Chen collaborates with Bob Wang on NLP research",
        },
    ],
}

SAMPLE_EMBEDDING = [0.1] * 384  # Simulated embedding vector


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j client."""
    client = MagicMock(spec=Neo4jClient)
    client.run_query.return_value = []
    client.run_write.return_value = []
    return client


@pytest.fixture
def mock_llm():
    """Mock LLM client with chat_json method."""
    llm = MagicMock()
    llm.chat_json.return_value = SAMPLE_EXTRACTION_RESULT
    return llm


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    svc = MagicMock(spec=EmbeddingService)
    svc.encode.return_value = [SAMPLE_EMBEDDING]
    svc.encode_single.return_value = SAMPLE_EMBEDDING
    svc.dimensions = 384
    return svc


@pytest.fixture
def entity_extractor(mock_llm):
    """EntityExtractor with mocked LLM."""
    return EntityExtractor(mock_llm)


@pytest.fixture
def episode_processor(mock_neo4j, entity_extractor, mock_embedding_service):
    """EpisodeProcessor with all dependencies mocked."""
    return EpisodeProcessor(mock_neo4j, entity_extractor, mock_embedding_service)


@pytest.fixture
def graph_service(mock_neo4j, mock_embedding_service):
    """LocalGraphService with mocked dependencies."""
    extractor = EntityExtractor(MagicMock())
    extractor._llm.chat_json.return_value = SAMPLE_EXTRACTION_RESULT
    return LocalGraphService(mock_neo4j, extractor, mock_embedding_service)
