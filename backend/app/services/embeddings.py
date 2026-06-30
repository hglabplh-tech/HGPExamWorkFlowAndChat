from functools import lru_cache

from sentence_transformers import SentenceTransformer

from ..config import get_settings
from .model_router import resolve_torch_device


def model_for_profile(profile: str) -> str:
    settings = get_settings()
    return settings.embedding_model_quality if profile == "quality" else settings.embedding_model_economy


@lru_cache(maxsize=4)
def encoder(profile: str, requested_device: str) -> SentenceTransformer:
    return SentenceTransformer(model_for_profile(profile), device=resolve_torch_device(requested_device))


def encode(profile: str, texts: list[str], requested_device: str = "auto") -> list[list[float]]:
    values = encoder(profile, requested_device).encode(texts, normalize_embeddings=True)
    return values.tolist()

