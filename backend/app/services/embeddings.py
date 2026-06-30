# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for embeddings."""
from functools import lru_cache
from pathlib import Path

from sentence_transformers import SentenceTransformer

from ..config import get_settings
from .model_router import resolve_torch_device


def model_for_profile(profile: str) -> str:
    """Perform the model for profile operation."""
    settings = get_settings()
    trained = Path(settings.model_output_dir) / "research_retrieval" / "current"
    if profile == "economy" and trained.exists():
        return str(trained.resolve())
    return settings.embedding_model_quality if profile == "quality" else settings.embedding_model_economy


@lru_cache(maxsize=4)
def encoder(model_name: str, requested_device: str) -> SentenceTransformer:
    """Perform the encoder operation."""
    return SentenceTransformer(model_name, device=resolve_torch_device(requested_device))


def encode(profile: str, texts: list[str], requested_device: str = "auto") -> list[list[float]]:
    """Perform the encode operation."""
    values = encoder(model_for_profile(profile), requested_device).encode(texts, normalize_embeddings=True)
    return values.tolist()
