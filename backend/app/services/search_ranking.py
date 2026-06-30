"""Pure hybrid-search ranking utilities for HcpXmlWorkflowChat.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from collections.abc import Iterable

from ..schemas import SearchHit


class HybridRanker:
    """Normalize and combine independent retrieval channels."""

    @staticmethod
    def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        """Return non-negative channel weights whose sum equals one."""
        if any(value < 0 for value in weights.values()):
            raise ValueError("Search weights cannot be negative")
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("At least one search weight must be positive")
        return {name: value / total for name, value in weights.items()}

    @staticmethod
    def strongest(items: Iterable[SearchHit]) -> list[SearchHit]:
        """Keep only the highest-scoring duplicate search hit."""
        reduced: dict[tuple[str, object], SearchHit] = {}
        for item in items:
            key = (item.kind, item.id)
            if key not in reduced or item.score > reduced[key].score:
                reduced[key] = item
        return list(reduced.values())

    @classmethod
    def fuse(
        cls,
        channels: dict[str, list[SearchHit]],
        weights: dict[str, float],
    ) -> list[SearchHit]:
        """Fuse channels with max-score normalization and weighted summation."""
        normalized_weights = cls.normalize_weights(weights)
        fused: dict[tuple[str, object], tuple[SearchHit, float]] = {}
        components: dict[tuple[str, object], dict[str, float]] = {}
        for channel_name, items in channels.items():
            ranked = cls.strongest(items)
            maximum = max((item.score for item in ranked), default=0.0) or 1.0
            for item in ranked:
                key = (item.kind, item.id)
                old_item, old_score = fused.get(key, (item, 0.0))
                contribution = normalized_weights.get(channel_name, 0.0) * max(
                    0.0, item.score / maximum
                )
                components.setdefault(key, {})[channel_name] = round(contribution, 6)
                fused[key] = (old_item, old_score + contribution)
        result = [
            item.model_copy(update={"score": score, "score_components": components[key]})
            for key, (item, score) in fused.items()
        ]
        return sorted(result, key=lambda item: item.score, reverse=True)
