"""Tests for embedding service."""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from app.services.local_graph.embedding_service import EmbeddingService


class TestEmbeddingService:
    def test_init_default_model(self):
        svc = EmbeddingService()
        assert "Qwen" in svc._model_name
        assert svc._model is None

    def test_init_custom_model(self):
        svc = EmbeddingService(model_name="custom/model")
        assert svc._model_name == "custom/model"

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_empty_list(self, mock_ensure):
        svc = EmbeddingService()
        result = svc.encode([])
        assert result == []
        mock_ensure.assert_not_called()

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_calls_model(self, mock_ensure):
        svc = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        svc._model = mock_model

        result = svc.encode(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 3
        mock_model.encode.assert_called_once()

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_single(self, mock_ensure):
        svc = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5, 0.6]])
        svc._model = mock_model

        result = svc.encode_single("test text")

        assert len(result) == 2
        assert result[0] == pytest.approx(0.5)

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_single_empty(self, mock_ensure):
        svc = EmbeddingService()
        result = svc.encode_single("")
        assert result == []

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_single_whitespace(self, mock_ensure):
        svc = EmbeddingService()
        result = svc.encode_single("   ")
        assert result == []

    def test_similarity(self):
        svc = EmbeddingService()
        # Identical vectors should have similarity ~1.0
        vec = [0.1, 0.2, 0.3, 0.4]
        sim = svc.similarity(vec, vec)
        assert sim == pytest.approx(1.0, abs=0.01)

    def test_similarity_orthogonal(self):
        svc = EmbeddingService()
        sim = svc.similarity([1, 0, 0], [0, 1, 0])
        assert sim == pytest.approx(0.0, abs=0.01)

    def test_similarity_empty_vectors(self):
        svc = EmbeddingService()
        assert svc.similarity([], [1, 2, 3]) == 0.0
        assert svc.similarity([1, 2, 3], []) == 0.0

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_dimensions_property(self, mock_ensure):
        svc = EmbeddingService()
        svc._dimensions = 384
        assert svc.dimensions == 384

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_multiple_texts(self, mock_ensure):
        svc = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([
            [0.1, 0.2],
            [0.3, 0.4],
            [0.5, 0.6],
        ])
        svc._model = mock_model

        result = svc.encode(["a", "b", "c"])

        assert len(result) == 3
        assert all(len(v) == 2 for v in result)

    @patch("app.services.local_graph.embedding_service.EmbeddingService._ensure_model")
    def test_encode_cleans_whitespace(self, mock_ensure):
        svc = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1]])
        svc._model = mock_model

        svc.encode(["  hello  "])

        call_args = mock_model.encode.call_args[0][0]
        assert call_args == ["hello"]
