"""Tests for Neo4j client wrapper."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.local_graph.neo4j_client import Neo4jClient


class TestNeo4jClient:
    def test_init(self):
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        assert client._uri == "bolt://localhost:7687"
        assert client._user == "neo4j"
        assert client._password == "password"
        assert client._database == "neo4j"
        assert client._driver is None

    def test_init_custom_database(self):
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "pw", database="mydb")
        assert client._database == "mydb"

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_driver_lazy_creation(self, mock_gdb):
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        assert client._driver is None

        driver = client.driver
        assert driver is mock_driver
        mock_gdb.driver.assert_called_once_with(
            "bolt://localhost:7687", auth=("neo4j", "password")
        )

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_driver_reuses_instance(self, mock_gdb):
        mock_gdb.driver.return_value = MagicMock()
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")

        driver1 = client.driver
        driver2 = client.driver
        assert driver1 is driver2
        mock_gdb.driver.assert_called_once()

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_close(self, mock_gdb):
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        _ = client.driver  # Force creation
        client.close()

        mock_driver.close.assert_called_once()
        assert client._driver is None

    def test_close_when_not_connected(self):
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        client.close()  # Should not raise

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_verify_connectivity_success(self, mock_gdb):
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        assert client.verify_connectivity() is True
        mock_driver.verify_connectivity.assert_called_once()

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_verify_connectivity_failure(self, mock_gdb):
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = Exception("Connection refused")
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        assert client.verify_connectivity() is False

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_run_query(self, mock_gdb):
        mock_record = MagicMock()
        mock_record.data.return_value = {"name": "Alice", "uuid": "123"}

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_record])

        mock_session = MagicMock()
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        results = client.run_query("MATCH (n) RETURN n.name", {"param": "value"})

        assert len(results) == 1
        assert results[0]["name"] == "Alice"

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_run_write(self, mock_gdb):
        mock_record = MagicMock()
        mock_record.data.return_value = {"uuid": "new-123"}

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_record])

        mock_session = MagicMock()
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute_write.side_effect = lambda fn: fn(mock_session)
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        results = client.run_write("CREATE (n:Test) RETURN n.uuid")

        assert len(results) == 1
        assert results[0]["uuid"] == "new-123"

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_ensure_indexes(self, mock_gdb):
        mock_session = MagicMock()
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute_write.side_effect = lambda fn: fn(mock_session)
        mock_session.run.return_value = iter([])

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        client.ensure_indexes()  # Should not raise

    @patch("app.services.local_graph.neo4j_client.GraphDatabase")
    def test_clear_graph(self, mock_gdb):
        mock_session = MagicMock()
        mock_session.__enter__ = lambda self: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute_write.side_effect = lambda fn: fn(mock_session)
        mock_session.run.return_value = iter([])

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        client.clear_graph("test-graph")

        # Should have been called 4 times (episodes, entities, ontology, graph)
        assert mock_session.execute_write.call_count == 4
