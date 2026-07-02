# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for model router."""
from dataclasses import dataclass

from ..config import get_settings


@dataclass(frozen=True)
class ModelDecision:
    """Represent modeldecision."""
    embedding_model: str
    reranker_model: str | None
    device: str
    reason: str


def query_complexity(query: str) -> int:
    """Perform the query complexity operation."""
    words = query.split()
    score = len(words)
    score += 8 if any(mark in query for mark in ("?", ":", ";")) else 0
    score += 12 if any(word.lower() in {"compare", "explain", "evaluate", "warum", "vergleiche"} for word in words) else 0
    return score


def select_models(query: str, profile: str | None = None, device: str | None = None) -> ModelDecision:
    """Perform the select models operation."""
    settings = get_settings()
    profile = profile or settings.embedding_profile
    complexity = query_complexity(query)
    economy = profile == "economy"
    embedding = settings.embedding_model_economy if economy else settings.embedding_model_quality
    settings.require_allowed_model(embedding)
    reranker = None
    reason = "fast multilingual sentence embedding"
    if complexity >= 22:
        reranker = settings.reranker_model_mbert if economy else settings.reranker_model_xlm_roberta
        settings.require_allowed_model(reranker)
        reason = "complex query: retrieve with sentence embeddings, then rerank with a multilingual cross-encoder"
    return ModelDecision(embedding, reranker, device or settings.compute_device, reason)


def resolve_torch_device(requested: str = "auto") -> str:
    """Perform the resolve torch device operation."""
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    try:
        import torch_xla.core.xla_model as xm
        return str(xm.xla_device())
    except ImportError:
        return "cpu"
