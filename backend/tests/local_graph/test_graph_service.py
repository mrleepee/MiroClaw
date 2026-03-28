"""Tests for LocalGraphService (main interface)."""

import json
import pytest
from unittest.mock import MagicMock, patch, call

from app.services.local_graph.models import (
    GraphNode,
    GraphEdge,
    Episode,
    EpisodeData,
    SearchResults,
)
from app.services.local_graph.graph_service import (
    LocalGraphService,
    _row_to_node,
    _row_to_edge,
    _normalize_ontology_types,
)


class TestLocalGraphServiceCreate:
    def test_create_graph(self, graph_service, mock_neo4j):
        graph_service.create(graph_id="g1", name="Test Graph", description="A test")
        mock_neo4j.run_write.assert_called_once()
        args = mock_neo4j.run_write.call_args
        assert "g1" in str(args)

    def test_delete_graph(self, graph_service, mock_neo4j):
        graph_service.delete("g1")
        mock_neo4j.clear_graph.assert_called_once_with("g1")


class TestLocalGraphServiceOntology:
    def test_set_ontology(self, graph_service, mock_neo4j):
        graph_service.set_ontology(
            graph_ids=["g1"],
            entities={"Person": {"description": "A person"}},
            edges={"KNOWS": {"description": "Knows"}},
        )
        mock_neo4j.run_write.assert_called_once()
        assert "g1" in graph_service._ontology_cache

    def test_set_ontology_multiple_graphs(self, graph_service, mock_neo4j):
        graph_service.set_ontology(
            graph_ids=["g1", "g2"],
            entities={"Person": {"description": "A person"}},
            edges={},
        )
        assert mock_neo4j.run_write.call_count == 2
        assert "g1" in graph_service._ontology_cache
        assert "g2" in graph_service._ontology_cache

    def test_get_ontology_from_cache(self, graph_service):
        from app.services.local_graph.models import OntologyDefinition

        graph_service._ontology_cache["g1"] = OntologyDefinition(
            entity_types={"Person": {}}, edge_types={}
        )
        ontology = graph_service._get_ontology("g1")
        assert "Person" in ontology.entity_types

    def test_get_ontology_from_neo4j(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [{
            "entity_types": '{"Person": {"description": "A person"}}',
            "edge_types": "{}",
        }]
        ontology = graph_service._get_ontology("g1")
        assert "Person" in ontology.entity_types

    def test_get_ontology_not_found(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        ontology = graph_service._get_ontology("g1")
        assert ontology.entity_types == {}


class TestLocalGraphServiceEpisodes:
    def test_add_batch(self, graph_service, mock_neo4j):
        episodes = [
            EpisodeData(data="Text one"),
            EpisodeData(data="Text two"),
        ]
        mock_neo4j.run_query.return_value = []
        mock_neo4j.run_write.return_value = [{
            "uuid": "n1", "name": "A", "summary": "", "labels_json": "[]",
            "attributes": "{}", "created_at": "", "created": True,
        }]

        result = graph_service.add_batch("g1", episodes)

        assert len(result) == 2
        assert all(isinstance(ep, Episode) for ep in result)
        assert result[0].graph_id == "g1"

    def test_add_single(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        mock_neo4j.run_write.return_value = [{
            "uuid": "n1", "name": "A", "summary": "", "labels_json": "[]",
            "attributes": "{}", "created_at": "", "created": True,
        }]

        graph_service.add("g1", type="text", data="Some action happened")

        # Should have created an episode
        assert mock_neo4j.run_write.called


class TestLocalGraphServiceSearch:
    def test_search_returns_search_results(self, graph_service, mock_neo4j, mock_embedding_service):
        mock_neo4j.run_query.return_value = [{
            "uuid": "n1", "name": "Alice", "summary": "A researcher",
            "labels_json": '["Entity", "Person"]', "attributes": "{}",
            "created_at": "2024-01-01", "score": 0.95,
        }]

        result = graph_service.search("g1", query="Who is Alice?", limit=5, scope="nodes")

        assert isinstance(result, SearchResults)
        mock_embedding_service.encode_single.assert_called_with("Who is Alice?")

    def test_search_empty_query_embedding(self, graph_service, mock_embedding_service):
        mock_embedding_service.encode_single.return_value = []
        result = graph_service.search("g1", query="test")
        assert result.edges == []
        assert result.nodes == []

    def test_search_edges_scope(self, graph_service, mock_neo4j, mock_embedding_service):
        mock_neo4j.run_query.return_value = [{
            "uuid": "e1", "name": "WORKS_AT", "fact": "Alice works at TechCorp",
            "source_uuid": "n1", "target_uuid": "n2",
            "created_at": None, "valid_at": None,
            "invalid_at": None, "expired_at": None,
        }]

        result = graph_service.search("g1", query="employment", scope="edges")
        assert isinstance(result, SearchResults)

    def test_search_both_scope(self, graph_service, mock_neo4j, mock_embedding_service):
        mock_neo4j.run_query.return_value = []
        result = graph_service.search("g1", query="test", scope="both")
        assert isinstance(result, SearchResults)


class TestNodeNamespace:
    def test_get_by_graph_id(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [
            {"uuid": "n1", "name": "Alice", "summary": "Person",
             "labels_json": '["Entity", "Person"]', "attributes": "{}",
             "created_at": "2024-01-01"},
            {"uuid": "n2", "name": "Bob", "summary": "Person",
             "labels_json": '["Entity", "Person"]', "attributes": "{}",
             "created_at": "2024-01-01"},
        ]
        nodes = graph_service.node.get_by_graph_id("g1")
        assert len(nodes) == 2
        assert nodes[0].name == "Alice"
        assert nodes[1].name == "Bob"

    def test_get_by_graph_id_with_cursor(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        graph_service.node.get_by_graph_id("g1", limit=50, uuid_cursor="cursor-uuid")

        call_args = mock_neo4j.run_query.call_args
        params = call_args[0][1]
        assert params["cursor"] == "cursor-uuid"
        assert params["limit"] == 50

    def test_get_single_node(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [{
            "uuid": "n1", "name": "Alice", "summary": "A person",
            "labels_json": '["Entity", "Person"]',
            "attributes": '{"role": "Researcher"}',
            "created_at": "2024-01-01", "graph_id": "g1",
        }]

        node = graph_service.node.get(uuid_="n1")
        assert node is not None
        assert node.name == "Alice"
        assert node.uuid_ == "n1"

    def test_get_single_node_not_found(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        node = graph_service.node.get(uuid_="nonexistent")
        assert node is None

    def test_get_entity_edges(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [{
            "uuid": "e1", "name": "WORKS_AT",
            "fact": "Alice works at TechCorp",
            "source_uuid": "n1", "target_uuid": "n2",
            "graph_id": "g1",
            "created_at": "2024-01-01", "valid_at": None,
            "invalid_at": None, "expired_at": None,
        }]

        edges = graph_service.node.get_entity_edges("n1")
        assert len(edges) == 1
        assert edges[0].fact == "Alice works at TechCorp"


class TestEdgeNamespace:
    def test_get_by_graph_id(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [{
            "uuid": "e1", "name": "WORKS_AT",
            "fact": "Alice works here",
            "source_uuid": "n1", "target_uuid": "n2",
            "created_at": None, "valid_at": None,
            "invalid_at": None, "expired_at": None,
        }]

        edges = graph_service.edge.get_by_graph_id("g1")
        assert len(edges) == 1
        assert edges[0].name == "WORKS_AT"

    def test_get_by_graph_id_with_cursor(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        graph_service.edge.get_by_graph_id("g1", limit=50, uuid_cursor="cursor-uuid")

        call_args = mock_neo4j.run_query.call_args
        params = call_args[0][1]
        assert params["cursor"] == "cursor-uuid"


class TestEpisodeNamespace:
    def test_get_episode(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = [{
            "uuid": "ep-1", "data": "Some text", "type": "text",
            "processed": True, "graph_id": "g1",
            "created_at": "2024-01-01",
        }]

        ep = graph_service.episode.get(uuid_="ep-1")
        assert ep is not None
        assert ep.uuid_ == "ep-1"
        assert ep.processed is True

    def test_get_episode_not_found(self, graph_service, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        ep = graph_service.episode.get(uuid_="nonexistent")
        assert ep is None


class TestHelperFunctions:
    def test_row_to_node(self):
        row = {
            "uuid": "n1", "name": "Alice", "summary": "Researcher",
            "labels_json": '["Entity", "Person"]',
            "attributes": '{"role": "Scientist"}',
            "created_at": "2024-01-01",
        }
        node = _row_to_node(row, "g1")
        assert node.uuid_ == "n1"
        assert node.name == "Alice"
        assert "Person" in node.labels
        assert node.attributes["role"] == "Scientist"
        assert node.graph_id == "g1"

    def test_row_to_node_invalid_json(self):
        row = {
            "uuid": "n1", "name": "Alice", "summary": "",
            "labels_json": "not-json",
            "attributes": "not-json",
            "created_at": None,
        }
        node = _row_to_node(row, "g1")
        assert node.labels == ["Entity"]
        assert node.attributes == {}

    def test_row_to_node_none_values(self):
        row = {
            "uuid": "n1", "name": "Alice",
            "summary": None, "labels_json": None,
            "attributes": None, "created_at": None,
        }
        node = _row_to_node(row, "g1")
        assert node.summary == ""
        assert node.labels == ["Entity"]

    def test_row_to_edge(self):
        row = {
            "uuid": "e1", "name": "WORKS_AT",
            "fact": "Alice works at TechCorp",
            "source_uuid": "n1", "target_uuid": "n2",
            "created_at": "2024-01-01",
            "valid_at": "2024-01-01",
            "invalid_at": None, "expired_at": None,
        }
        edge = _row_to_edge(row)
        assert edge.uuid_ == "e1"
        assert edge.name == "WORKS_AT"
        assert edge.source_node_uuid == "n1"
        assert edge.target_node_uuid == "n2"
        assert edge.valid_at == "2024-01-01"

    def test_normalize_ontology_dict(self):
        result = _normalize_ontology_types({
            "Person": {"description": "A person"},
        })
        assert result == {"Person": {"description": "A person"}}

    def test_normalize_ontology_tuple(self):
        result = _normalize_ontology_types({
            "WORKS_AT": ("SomeModel", ["constraint1"]),
        })
        assert "WORKS_AT" in result
        assert "model" in result["WORKS_AT"]
