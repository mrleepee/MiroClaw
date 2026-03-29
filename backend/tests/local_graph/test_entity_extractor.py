"""Tests for entity extraction service."""

import pytest
from unittest.mock import MagicMock

from app.services.local_graph.entity_extractor import EntityExtractor

from .conftest import (
    SAMPLE_EXTRACTION_RESULT,
    SAMPLE_ONTOLOGY_DICT,
    SAMPLE_TEXT,
)


class TestEntityExtractor:
    def test_extract_returns_entities_and_relationships(self, entity_extractor):
        result = entity_extractor.extract(SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT)

        assert "entities" in result
        assert "relationships" in result
        assert len(result["entities"]) > 0
        assert len(result["relationships"]) > 0

    def test_extract_entity_structure(self, entity_extractor):
        result = entity_extractor.extract(SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT)

        entity = result["entities"][0]
        assert "name" in entity
        assert "type" in entity
        assert "summary" in entity
        assert "attributes" in entity

    def test_extract_relationship_structure(self, entity_extractor):
        result = entity_extractor.extract(SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT)

        rel = result["relationships"][0]
        assert "source" in rel
        assert "target" in rel
        assert "type" in rel
        assert "fact" in rel

    def test_extract_empty_text_returns_empty(self, entity_extractor):
        result = entity_extractor.extract("", SAMPLE_ONTOLOGY_DICT)
        assert result == {"entities": [], "relationships": []}

    def test_extract_whitespace_text_returns_empty(self, entity_extractor):
        result = entity_extractor.extract("   ", SAMPLE_ONTOLOGY_DICT)
        assert result == {"entities": [], "relationships": []}

    def test_extract_filters_invalid_entity_types(self, mock_llm):
        mock_llm.chat_json.return_value = {
            "entities": [
                {"name": "Alice", "type": "Person", "summary": "A person"},
                {"name": "Magic", "type": "Concept", "summary": "Not in ontology"},
            ],
            "relationships": [],
        }
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract("text", SAMPLE_ONTOLOGY_DICT)

        names = [e["name"] for e in result["entities"]]
        assert "Alice" in names
        assert "Magic" not in names

    def test_extract_filters_invalid_edge_types(self, mock_llm):
        mock_llm.chat_json.return_value = {
            "entities": [
                {"name": "A", "type": "Person", "summary": ""},
                {"name": "B", "type": "Person", "summary": ""},
            ],
            "relationships": [
                {"source": "A", "target": "B", "type": "WORKS_AT", "fact": "Valid"},
                {"source": "A", "target": "B", "type": "LOVES", "fact": "Invalid type"},
            ],
        }
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract("text", SAMPLE_ONTOLOGY_DICT)

        types = [r["type"] for r in result["relationships"]]
        assert "WORKS_AT" in types
        assert "LOVES" not in types

    def test_extract_handles_llm_error_gracefully(self, mock_llm):
        mock_llm.chat_json.side_effect = Exception("API error")
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract(SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT)
        assert result == {"entities": [], "relationships": []}

    def test_extract_handles_malformed_llm_response(self, mock_llm):
        mock_llm.chat_json.return_value = {"entities": "not a list"}
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract(SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT)
        assert result["entities"] == []

    def test_extract_with_existing_entity_names(self, entity_extractor, mock_llm):
        entity_extractor.extract(
            SAMPLE_TEXT, SAMPLE_ONTOLOGY_DICT,
            existing_entity_names=["Alice Chen", "TechCorp"]
        )

        # Verify the prompt included existing names
        call_args = mock_llm.chat_json.call_args
        messages = call_args[1].get("messages") or call_args[0][0]
        # Implementation combines system + user into a single message
        prompt_content = messages[0]["content"]
        assert "Alice Chen" in prompt_content

    def test_extract_filters_entities_missing_name(self, mock_llm):
        mock_llm.chat_json.return_value = {
            "entities": [
                {"name": "", "type": "Person", "summary": "No name"},
                {"name": "Valid", "type": "Person", "summary": "Has name"},
            ],
            "relationships": [],
        }
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract("text", SAMPLE_ONTOLOGY_DICT)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Valid"

    def test_extract_filters_relationships_missing_fact(self, mock_llm):
        mock_llm.chat_json.return_value = {
            "entities": [
                {"name": "A", "type": "Person", "summary": ""},
            ],
            "relationships": [
                {"source": "A", "target": "B", "type": "WORKS_AT", "fact": ""},
                {"source": "A", "target": "B", "type": "WORKS_AT", "fact": "Valid fact"},
            ],
        }
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract("text", SAMPLE_ONTOLOGY_DICT)
        assert len(result["relationships"]) == 1

    def test_extract_with_empty_ontology(self, mock_llm):
        """With no type constraints, all entities/relationships pass through."""
        mock_llm.chat_json.return_value = {
            "entities": [
                {"name": "Alice", "type": "Anything", "summary": "test"},
            ],
            "relationships": [
                {"source": "A", "target": "B", "type": "ANY", "fact": "test"},
            ],
        }
        extractor = EntityExtractor(mock_llm)
        result = extractor.extract("text", {"entity_types": {}, "edge_types": {}})
        assert len(result["entities"]) == 1
        assert len(result["relationships"]) == 1
