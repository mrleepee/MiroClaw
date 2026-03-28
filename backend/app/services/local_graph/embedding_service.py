"""Embedding service using Qwen3-Embedding-4B for semantic search."""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Default model - can be overridden via config
DEFAULT_MODEL_NAME = "Qwen/Qwen3-Embedding-4B"
# Fallback for environments with limited resources
FALLBACK_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """Generates text embeddings for semantic search.

    Uses Qwen3-Embedding-4B by default, with a lightweight fallback option.
    Embeddings are stored in Neo4j vector indexes for native similarity search.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or DEFAULT_MODEL_NAME
        self._model = None
        self._dimensions: Optional[int] = None

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions (loads model if needed)."""
        if self._dimensions is None:
            self._ensure_model()
        return self._dimensions  # type: ignore[return-value]

    def _ensure_model(self):
        """Lazy-load the embedding model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name, trust_remote_code=True)
            # Determine dimensions from a test embedding
            test_emb = self._model.encode(["test"], normalize_embeddings=True)
            self._dimensions = test_emb.shape[1]
            logger.info(
                f"Embedding model loaded: {self._model_name} "
                f"(dimensions={self._dimensions})"
            )
        except Exception as e:
            logger.warning(
                f"Failed to load {self._model_name}: {e}. "
                f"Falling back to {FALLBACK_MODEL_NAME}"
            )
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(FALLBACK_MODEL_NAME)
                test_emb = self._model.encode(["test"], normalize_embeddings=True)
                self._dimensions = test_emb.shape[1]
                logger.info(
                    f"Fallback model loaded: {FALLBACK_MODEL_NAME} "
                    f"(dimensions={self._dimensions})"
                )
            except Exception as e2:
                logger.error(f"Failed to load fallback model: {e2}")
                raise RuntimeError(
                    "Cannot load any embedding model. "
                    "Install sentence-transformers: pip install sentence-transformers"
                ) from e2

    def encode(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        if not texts:
            return []

        self._ensure_model()

        # Clean inputs
        cleaned = [t.strip() if t else "" for t in texts]
        embeddings = self._model.encode(  # type: ignore[union-attr]
            cleaned, normalize_embeddings=True, show_progress_bar=False
        )

        return embeddings.tolist()

    def encode_single(self, text: str) -> List[float]:
        """Generate embedding for a single text string."""
        if not text or not text.strip():
            return []
        result = self.encode([text])
        return result[0] if result else []

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Compute cosine similarity between two embeddings."""
        if not embedding1 or not embedding2:
            return 0.0
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))
