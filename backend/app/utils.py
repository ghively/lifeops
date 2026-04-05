"""Shared utility functions."""
import hashlib
import logging

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error("Error computing hash for %s: %s", file_path, e)
        return ""
