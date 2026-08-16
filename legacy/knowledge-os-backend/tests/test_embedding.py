"""
Tests for the embedding service.
"""

import asyncio
import time

import numpy as np
import pytest


class TestEmbeddingService:
    """Test cases for embedding generation service."""

    @pytest.mark.asyncio
    async def test_embed_text_basic(self, mock_embedding_service):
        """Test basic text embedding."""
        text = "This is a test sentence"
        vector = await mock_embedding_service.embed_text(text)

        assert vector is not None
        assert len(vector) == 384
        assert all(isinstance(v, (int, float, np.floating)) for v in vector)

    @pytest.mark.asyncio
    async def test_embed_text_empty(self, mock_embedding_service):
        """Test embedding empty text."""
        text = ""
        vector = await mock_embedding_service.embed_text(text)

        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_embed_text_unicode(self, mock_embedding_service):
        """Test embedding text with Unicode characters."""
        text = "Test with emoji 🎉 and 中文 characters"
        vector = await mock_embedding_service.embed_text(text)

        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_embed_text_long(self, mock_embedding_service):
        """Test embedding long text."""
        text = "word " * 1000
        vector = await mock_embedding_service.embed_text(text)

        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_embed_texts_batch(self, mock_embedding_service):
        """Test batch embedding of multiple texts."""
        texts = ["First text", "Second text", "Third text"]
        vectors = await mock_embedding_service.embed_texts(texts)

        assert len(vectors) == len(texts)
        assert all(len(v) == 384 for v in vectors)

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self, mock_embedding_service):
        """Test embedding empty list of texts."""
        vectors = await mock_embedding_service.embed_texts([])
        assert vectors == []

    @pytest.mark.asyncio
    async def test_embed_texts_single(self, mock_embedding_service):
        """Test embedding single text in batch."""
        texts = ["Single text"]
        vectors = await mock_embedding_service.embed_texts(texts)

        assert len(vectors) == 1
        assert len(vectors[0]) == 384

    @pytest.mark.asyncio
    async def test_embed_image_basic(self, mock_embedding_service):
        """Test basic image embedding."""
        image_path = "/path/to/image.jpg"
        vector = await mock_embedding_service.embed_image(image_path)

        assert vector is not None
        assert len(vector) == 512

    @pytest.mark.asyncio
    async def test_deterministic_embeddings(self, mock_embedding_service):
        """Test that same input produces same embedding."""
        text = "Deterministic test"
        vector1 = await mock_embedding_service.embed_text(text)
        vector2 = await mock_embedding_service.embed_text(text)
        np.testing.assert_array_equal(vector1, vector2)

    @pytest.mark.asyncio
    async def test_different_inputs_different_embeddings(self, mock_embedding_service):
        """Test that different inputs produce different embeddings."""
        vector1 = await mock_embedding_service.embed_text("text one")
        vector2 = await mock_embedding_service.embed_text("text two")
        assert not np.array_equal(vector1, vector2)

    @pytest.mark.asyncio
    async def test_embedding_normalization(self, mock_embedding_service):
        """Test that embeddings are normalized."""
        text = "Test text"
        vector = await mock_embedding_service.embed_text(text)
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 0.01  # Approximately unit length

    @pytest.mark.asyncio
    async def test_embedding_values_range(self, mock_embedding_service):
        """Test that embedding values are in expected range."""
        text = "Test text"
        vector = await mock_embedding_service.embed_text(text)
        assert all(-1 <= v <= 1 for v in vector)


class TestEmbeddingFallback:
    """Test cases for embedding fallback mode."""

    @pytest.mark.asyncio
    async def test_fallback_mode_deterministic(self, mock_embedding_service):
        """Test that fallback mode produces deterministic vectors."""
        vector1 = await mock_embedding_service.embed_text("test")
        vector2 = await mock_embedding_service.embed_text("test")
        np.testing.assert_array_equal(vector1, vector2)

    @pytest.mark.asyncio
    async def test_fallback_different_inputs(self, mock_embedding_service):
        """Test that fallback mode produces different vectors for different inputs."""
        vector1 = await mock_embedding_service.embed_text("apple")
        vector2 = await mock_embedding_service.embed_text("banana")
        assert not np.array_equal(vector1, vector2)

    @pytest.mark.asyncio
    async def test_fallback_vector_dimensions(self, mock_embedding_service):
        """Test that fallback produces correct dimensions."""
        vector = await mock_embedding_service.embed_text("test")
        assert len(vector) == 384


class TestEmbeddingModelLoading:
    """Test cases for embedding model loading."""

    @pytest.mark.asyncio
    async def test_initialize_service(self):
        """Test initializing embedding service."""
        from app.services.embedding import embedding_service

        await embedding_service.initialize()

    @pytest.mark.asyncio
    async def test_close_service(self):
        """Test closing embedding service."""
        from app.services.embedding import embedding_service

        await embedding_service.close()

    @pytest.mark.asyncio
    async def test_service_singleton(self):
        """Test that embedding service is a singleton."""
        from app.services.embedding import embedding_service
        from app.services.embedding import embedding_service as es2

        assert embedding_service is es2


class TestEmbeddingPerformance:
    """Test cases for embedding service performance."""

    @pytest.mark.asyncio
    async def test_batch_embedding_performance(self, mock_embedding_service):
        """Test batch embedding performance."""
        texts = ["text"] * 100
        start = time.time()
        vectors = await mock_embedding_service.embed_texts(texts)
        elapsed = time.time() - start

        assert len(vectors) == 100
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_single_embedding_performance(self, mock_embedding_service):
        """Test single text embedding performance."""
        text = "This is a test of embedding performance"
        start = time.time()
        vector = await mock_embedding_service.embed_text(text)
        elapsed = time.time() - start

        assert len(vector) == 384
        assert elapsed < 1.0


class TestEmbeddingEdgeCases:
    """Test cases for embedding edge cases."""

    @pytest.mark.asyncio
    async def test_very_long_text(self, mock_embedding_service):
        """Test embedding very long text."""
        text = "word " * 10000
        vector = await mock_embedding_service.embed_text(text)
        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_special_characters_only(self, mock_embedding_service):
        """Test embedding text with only special characters."""
        text = "!@#$%^&*()_+-=[]{}|;:,.<>?/"
        vector = await mock_embedding_service.embed_text(text)
        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_newlines_and_tabs(self, mock_embedding_service):
        """Test embedding text with newlines and tabs."""
        text = "line1\nline2\tindented"
        vector = await mock_embedding_service.embed_text(text)
        assert vector is not None
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_numbers_and_mixed_content(self, mock_embedding_service):
        """Test embedding text with numbers and mixed content."""
        text = "Version 2.0 released on 2024-01-01 with 1000+ features!"
        vector = await mock_embedding_service.embed_text(text)
        assert vector is not None
        assert len(vector) == 384
