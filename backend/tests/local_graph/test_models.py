"""Tests for local_graph data models."""

import json
import pytest

from app.services.local_graph.models import (
    GraphNode,
    GraphEdge,
    Episode,
    EpisodeData,
    OntologyDefinition,
    SearchResults,
)


class TestGraphNode:
    def test_default_creation(self):
        node = GraphNode()
        assert node.uuid_ != ""
        assert node.uuid == node.uuid_  # property alias
        assert node.name == ""
        assert node.labels == ["Entity"]
        assert node.summary == ""
        assert node.attributes == {}
        assert node.created_at is not None

    def test_custom_creation(self):
        node = GraphNode(
            uuid_="test-uuid",
            name="Alice",
            labels=["Entity", "Person"],
            summary="A researcher",
            attributes={"role": "Scientist"},
            graph_id="graph-1",
        )
        assert node.uuid_ == "test-uuid"
        assert node.uuid == "test-uuid"
        assert node.name == "Alice"
        assert "Person" in node.labels
        assert node.attributes["role"] == "Scientist"
        assert node.graph_id == "graph-1"

    def test_uuid_property_alias(self):
        node = GraphNode(uuid_="abc-123")
        assert node.uuid == "abc-123"
        assert node.uuid_ == "abc-123"

    def test_unique_uuids(self):
        nodes = [GraphNode() for _ in range(10)]
        uuids = {n.uuid_ for n in nodes}
        assert len(uuids) == 10

    def test_embedding_excluded_from_repr(self):
        node = GraphNode(embedding=[0.1, 0.2, 0.3])
        assert "[0.1" not in repr(node)


class TestGraphEdge:
    def test_default_creation(self):
        edge = GraphEdge()
        assert edge.uuid_ != ""
        assert edge.uuid == edge.uuid_
        assert edge.name == ""
        assert edge.fact == ""
        assert edge.source_node_uuid == ""
        assert edge.target_node_uuid == ""
        assert edge.valid_at is None
        assert edge.invalid_at is None
        assert edge.expired_at is None

    def test_custom_creation(self):
        edge = GraphEdge(
            uuid_="edge-1",
            name="WORKS_AT",
            fact="Alice works at TechCorp",
            source_node_uuid="node-1",
            target_node_uuid="node-2",
            valid_at="2024-01-01T00:00:00",
        )
        assert edge.name == "WORKS_AT"
        assert edge.fact == "Alice works at TechCorp"
        assert edge.source_node_uuid == "node-1"
        assert edge.target_node_uuid == "node-2"
        assert edge.valid_at == "2024-01-01T00:00:00"

    def test_uuid_property_alias(self):
        edge = GraphEdge(uuid_="edge-abc")
        assert edge.uuid == "edge-abc"


class TestEpisode:
    def test_default_creation(self):
        ep = Episode()
        assert ep.uuid_ != ""
        assert ep.data == ""
        assert ep.type == "text"
        assert ep.processed is False
        assert ep.graph_id == ""

    def test_custom_creation(self):
        ep = Episode(
            uuid_="ep-1",
            data="Some text content",
            type="text",
            processed=True,
            graph_id="g1",
        )
        assert ep.data == "Some text content"
        assert ep.processed is True

    def test_uuid_property_alias(self):
        ep = Episode(uuid_="ep-xyz")
        assert ep.uuid == "ep-xyz"


class TestEpisodeData:
    def test_default(self):
        ed = EpisodeData()
        assert ed.data == ""
        assert ed.type == "text"

    def test_with_data(self):
        ed = EpisodeData(data="Hello world", type="text")
        assert ed.data == "Hello world"


class TestSearchResults:
    def test_empty(self):
        sr = SearchResults()
        assert sr.edges == []
        assert sr.nodes == []

    def test_with_results(self):
        node = GraphNode(name="Alice")
        edge = GraphEdge(fact="Alice works here")
        sr = SearchResults(edges=[edge], nodes=[node])
        assert len(sr.edges) == 1
        assert len(sr.nodes) == 1
        assert sr.nodes[0].name == "Alice"
        assert sr.edges[0].fact == "Alice works here"


class TestOntologyDefinition:
    def test_default(self):
        ont = OntologyDefinition()
        assert ont.entity_types == {}
        assert ont.edge_types == {}

    def test_with_types(self):
        ont = OntologyDefinition(
            entity_types={"Person": {"description": "A person"}},
            edge_types={"KNOWS": {"description": "Knows someone"}},
        )
        assert "Person" in ont.entity_types
        assert "KNOWS" in ont.edge_types
