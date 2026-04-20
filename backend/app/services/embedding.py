"""Embedding Service - Text and image embeddings"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import List

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

TEXT_EMBEDDING_DIMENSION = 384
IMAGE_EMBEDDING_DIMENSION = 512


class EmbeddingService:
    """Service for generating embeddings"""

    def __init__(self):
        self.text_model = None
        self.image_model = None
        self.image_processor = None
        self.loop = None

    async def initialize(self):
        """Initialize the embedding service - load models"""
        logger.info("Loading embedding models...")

        # Models are loaded lazily on first use
        # This avoids blocking startup

        logger.info("Embedding service initialized")

    async def close(self):
        """Close the embedding service"""
        logger.info("Embedding service closed")

    def _load_text_model(self):
        """Load text embedding model"""
        if self.text_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.text_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded text embedding model")
            except Exception as e:
                logger.warning(f"Falling back to deterministic text embeddings: {e}")
                self.text_model = False

    def _fallback_embedding(self, seed_text: str, dimensions: int) -> np.ndarray:
        """Generate a deterministic unit-length embedding from text."""
        if not seed_text:
            return np.zeros(dimensions, dtype=np.float32)

        vector = np.zeros(dimensions, dtype=np.float32)
        seed_bytes = seed_text.encode("utf-8", errors="ignore")

        for index in range(dimensions):
            digest = hashlib.sha256(seed_bytes + index.to_bytes(2, "little")).digest()
            value = int.from_bytes(digest[:4], "little", signed=False) / 0xFFFFFFFF
            vector[index] = (value * 2.0) - 1.0

        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text"""
        if not text:
            # Return zero vector for empty text
            return np.zeros(TEXT_EMBEDDING_DIMENSION, dtype=np.float32)

        self._load_text_model()
        if self.text_model is False:
            return self._fallback_embedding(text, TEXT_EMBEDDING_DIMENSION)

        # Run in thread pool to avoid blocking
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, lambda: self.text_model.encode(text, convert_to_numpy=True))

        return embedding

    async def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts"""
        if not texts:
            return []

        self._load_text_model()
        if self.text_model is False:
            return [self._fallback_embedding(text, TEXT_EMBEDDING_DIMENSION) for text in texts]

        # Run in thread pool
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, lambda: self.text_model.encode(texts, convert_to_numpy=True))

        return embeddings

    def _load_image_model(self):
        """Load image embedding model"""
        if self.image_model is None:
            try:
                from transformers import CLIPModel, CLIPProcessor

                self.image_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self.image_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                logger.info("Loaded image embedding model")
            except Exception as e:
                logger.warning(f"Falling back to deterministic image embeddings: {e}")
                self.image_model = False
                self.image_processor = False

    async def embed_image(self, image_path: str) -> np.ndarray:
        """Generate embedding for image"""
        self._load_image_model()
        if self.image_model is False:
            return self._fallback_embedding(str(Path(image_path).resolve()), IMAGE_EMBEDDING_DIMENSION)

        from PIL import Image

        # Load image
        image = Image.open(image_path)

        # Process
        inputs = self.image_processor(images=image, return_tensors="pt")

        # Run in thread pool
        loop = asyncio.get_running_loop()
        outputs = await loop.run_in_executor(None, lambda: self.image_model.get_image_features(**inputs))

        # Convert to numpy
        embedding = outputs.detach().numpy().flatten()

        return embedding


# Global embedding service instance
embedding_service = EmbeddingService()
