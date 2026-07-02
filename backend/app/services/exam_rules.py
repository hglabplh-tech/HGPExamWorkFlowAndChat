"""Transparent evaluation helpers for instructor-defined exam rules.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import re

from .academic_integrity import check_apa_citations


def evaluate_exam_rules(text: str, rules: dict, page_count: int | None = None) -> dict:
    """Evaluate format and weighted quality indicators without replacing review."""
    topic_terms = set(re.findall(r"\w+", str(rules.get("topic", "")).casefold()))
    text_terms = set(re.findall(r"\w+", text.casefold()))
    context = len(topic_terms & text_terms) / max(1, len(topic_terms))
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    design = min(1.0, len(paragraphs) / 5)
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    average_words = sum(len(part.split()) for part in sentences) / max(1, len(sentences))
    wording = max(0.0, 1.0 - abs(average_words - 18) / 30)
    citation_review = check_apa_citations(text)
    citations = min(1.0, citation_review.get("citation_count", 0) / 3) if citation_review.get("has_reference_section") else 0.0
    signals = {"context": context, "design": design, "wording": wording, "citations": citations}
    weights = rules.get("weights", {})
    weighted = sum(signals[name] * float(weights.get(name, 0)) for name in signals)
    page_check = None if page_count is None else rules.get("page_count_min", 1) <= page_count <= rules.get("page_count_max", 20)
    return {
        "weighted_score": round(weighted, 6),
        "signals": {name: round(value, 6) for name, value in signals.items()},
        "weights": weights,
        "page_count": page_count,
        "page_count_compliant": page_check,
        "requires_teacher_review": True,
    }
