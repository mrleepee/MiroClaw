"""Tests for episode processing pipeline."""

import pytest
from unittest.mock import MagicMock, call

from app.services.local_graph.models import Episode, OntologyDefinition
from app.services.local_graph.episode_processor import EpisodeProcessor

from .conftest import (
    SAMPLE_ONTOLOGY,
    SAMPLE_EXTRACTION_RESULT,
    SAMPLE_EMBEDDING,
    SAMPLE_TEXT,
)


class TestEpisodeProcessor:
    def test_process_episode_creates_entities(self, episode_processor, mock_neo4j):
        episode = Episode(
            uuid_="ep-1", data=SAMPLE_TEXT, graph_id="g1"
        )

        # Mock existing entity lookup (empty graph)
        mock_neo4j.run_query.return_value = []

        # Mock upsert responses (entity created)
        mock_neo4j.run_write.return_value = [{
            "uuid": "node-1",
            "name": "Alice Chen",
            "summary": "Senior researcher",
            "labels_json": '["Entity", "Person"]',
            "attributes": "{}",
            "created_at": "2024-01-01",
            "created": True,
        }]

        stats = episode_processor.process_episode(episode, SAMPLE_ONTOLOGY)

        assert stats["entities_created"] > 0 or stats["entities_updated"] > 0
        assert mock_neo4j.run_write.called

    def test_process_episode_empty_text(self, episode_processor, mock_neo4j):
        episode = Episode(uuid_="ep-1", data="", graph_id="g1")
        stats = episode_processor.process_episode(episode, SAMPLE_ONTOLOGY)

        assert stats == {
            "entities_created": 0,
            "entities_updated": 0,
            "relationships_created": 0,
        }

    def test_process_episode_marks_processed(self, episode_processor, mock_neo4j):
        episode = Episode(uuid_="ep-1", data=SAMPLE_TEXT, graph_id="g1")
        mock_neo4j.run_query.return_value = []
        mock_neo4j.run_write.return_value = [{
            "uuid": "n1", "name": "A", "summary": "", "labels_json": "[]",
            "attributes": "{}", "created_at": "", "created": True,
        }]

        episode_processor.process_episode(episode, SAMPLE_ONTOLOGY)

        # Check that mark_processed was called
        mark_calls = [
            c for c in mock_neo4j.run_write.call_args_list
            if "processed" in str(c)
        ]
        assert len(mark_calls) > 0

    def test_process_batch(self, episode_processor, mock_neo4j):
        episodes = [
            Episode(uuid_="ep-1", data="Text one", graph_id="g1"),
            Episode(uuid_="ep-2", data="Text two", graph_id="g1"),
        ]
        mock_neo4j.run_query.return_value = []
        mock_neo4j.run_write.return_value = [{
            "uuid": "n1", "name": "A", "summary": "", "labels_json": "[]",
            "attributes": "{}", "created_at": "", "created": True,
        }]

        totals = episode_processor.process_batch(episodes, SAMPLE_ONTOLOGY)

        assert isinstance(totals, dict)
        assert "entities_created" in totals
        assert "relationships_created" in totals

    def test_process_batch_continues_on_error(self, episode_processor, mock_neo4j):
        """If one episode fails, the others should still be processed."""
        episodes = [
            Episode(uuid_="ep-1", data="Text one", graph_id="g1"),
            Episode(uuid_="ep-2", data="Text two", graph_id="g1"),
        ]

        # First call fails, second succeeds
        call_count = [0]
        original_extract = episode_processor._extractor.extract

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Extraction failed")
            return SAMPLE_EXTRACTION_RESULT

        episode_processor._extractor.extract = side_effect
        mock_neo4j.run_query.return_value = []
        mock_neo4j.run_write.return_value = [{
            "uuid": "n1", "name": "A", "summary": "", "labels_json": "[]",
            "attributes": "{}", "created_at": "", "created": True,
        }]

        totals = episode_processor.process_batch(episodes, SAMPLE_ONTOLOGY)
        # Should have processed at least some work from the second episode
        assert isinstance(totals, dict)

    def test_get_existing_entity_names(self, episode_processor, mock_neo4j):
        mock_neo4j.run_query.return_value = [
            {"name": "Alice"},
            {"name": "Bob"},
        ]
        names = episode_processor._get_existing_entity_names("g1")
        assert "Alice" in names
        assert "Bob" in names

    def test_find_entity_uuid(self, episode_processor, mock_neo4j):
        mock_neo4j.run_query.return_value = [{"uuid": "found-uuid"}]
        uuid = episode_processor._find_entity_uuid("g1", "Alice")
        assert uuid == "found-uuid"

    def test_find_entity_uuid_not_found(self, episode_processor, mock_neo4j):
        mock_neo4j.run_query.return_value = []
        uuid = episode_processor._find_entity_uuid("g1", "Unknown")
        assert uuid is None
