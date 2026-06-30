# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for asag."""
import math
import re
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ..config import get_settings
from ..models import DisciplineScoringProfile, ExamQuestion
from .embeddings import encode
from .model_router import resolve_torch_device

TOKEN = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> set[str]:
    """Perform the tokens operation."""
    return {token.casefold() for token in TOKEN.findall(text)}


def jaccard(answer: str, reference: str) -> float:
    """Perform the jaccard operation."""
    left, right = tokens(answer), tokens(reference)
    return len(left & right) / len(left | right) if left or right else 1.0


def keyword_coverage(answer: str, keywords: list[str]) -> float | None:
    """Perform the keyword coverage operation."""
    if not keywords:
        return None
    normalized = " ".join(TOKEN.findall(answer.casefold()))
    return sum(" ".join(TOKEN.findall(keyword.casefold())) in normalized for keyword in keywords) / len(keywords)


def semantic_similarity(answer: str, reference: str, profile: str) -> float:
    """Perform the semantic similarity operation."""
    vectors = encode(profile, [answer, reference], get_settings().compute_device)
    cosine = sum(left * right for left, right in zip(vectors[0], vectors[1]))
    return max(0.0, min(1.0, cosine))


def length_adequacy(answer: str, reference: str) -> float:
    """Perform the length adequacy operation."""
    reference_length = max(1, len(TOKEN.findall(reference)))
    return min(1.0, len(TOKEN.findall(answer)) / reference_length)


@lru_cache(maxsize=3)
def trained_cross_encoder(model_path: str):
    """Perform the trained cross encoder operation."""
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model_path, device=resolve_torch_device(get_settings().compute_device))


def discipline_slug(value: str) -> str:
    """Perform the discipline slug operation."""
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "general"


def trained_scoring(reference: str, answer: str, discipline: str) -> float | None:
    """Perform the trained scoring operation."""
    current = Path(get_settings().model_output_dir) / "answer_scoring" / discipline_slug(discipline) / "current"
    if not current.exists():
        return None
    value = float(trained_cross_encoder(str(current.resolve())).predict([(reference, answer)])[0])
    return max(0.0, min(1.0, value))


@lru_cache(maxsize=1)
def nli_components():
    """Perform the nli components operation."""
    model_name = get_settings().nli_model
    device = resolve_torch_device(get_settings().compute_device)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device).eval()
    labels = {index: label.lower() for index, label in model.config.id2label.items()}
    entailment = next(index for index, label in labels.items() if "entail" in label)
    contradiction = next(index for index, label in labels.items() if "contrad" in label)
    return tokenizer, model, device, entailment, contradiction


def nli_probabilities(premise: str, hypothesis: str) -> tuple[float, float]:
    """Perform the nli probabilities operation."""
    tokenizer, model, device, entailment, contradiction = nli_components()
    values = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)
    values = {key: value.to(device) for key, value in values.items()}
    with torch.inference_mode():
        probabilities = model(**values).logits.softmax(dim=-1)[0]
    return float(probabilities[entailment]), float(probabilities[contradiction])


def fact_entailment(answer: str, facts: list[str]) -> float | None:
    """Perform the fact entailment operation."""
    if not facts:
        return None
    # The student's answer is the premise; each teacher-approved fact is a hypothesis.
    return sum(nli_probabilities(answer, fact)[0] for fact in facts) / len(facts)


def grade_answer(question: ExamQuestion, answer: str, profile: DisciplineScoringProfile) -> dict:
    """Perform the grade answer operation."""
    signals: dict[str, float | None] = {
        "jaccard": jaccard(answer, question.reference_answer),
        "keywords": keyword_coverage(answer, question.required_keywords),
        "semantic": semantic_similarity(answer, question.reference_answer, profile.semantic_profile),
        "trained_scoring": trained_scoring(question.reference_answer, answer, profile.discipline),
        "fact_entailment": None,
        "contradiction": None,
        "length": length_adequacy(answer, question.reference_answer),
    }
    warnings: list[str] = []
    if signals["trained_scoring"] is None and profile.grading_weights.get("trained_scoring", 0) > 0:
        warnings.append("No approved discipline-trained scoring model is active; other weights were renormalized")
    try:
        signals["fact_entailment"] = fact_entailment(answer, question.expected_facts)
        _, contradiction = nli_probabilities(question.reference_answer, answer)
        signals["contradiction"] = 1.0 - contradiction
    except Exception as error:
        warnings.append(f"NLI fact-check signal unavailable: {type(error).__name__}")

    available = {name: value for name, value in signals.items() if value is not None}
    denominator = sum(profile.grading_weights.get(name, 0.0) for name in available)
    if denominator <= 0:
        warnings.append("Configured weights do not cover available signals; equal fallback weights applied")
        applied_weights = {name: 1.0 / len(available) for name in available}
    else:
        applied_weights = {name: profile.grading_weights.get(name, 0.0) / denominator for name in available}
    normalized = sum(available[name] * applied_weights[name] for name in available)
    spread = math.sqrt(sum((value - normalized) ** 2 for value in available.values()) / len(available))
    if spread > 0.25:
        warnings.append("Scoring signals disagree; teacher review required")
    return {
        "score": round(normalized * question.max_score, 3),
        "max_score": question.max_score,
        "normalized_score": round(normalized, 6),
        "signals": {name: round(value, 6) if value is not None else None for name, value in signals.items()},
        "configured_weights": profile.grading_weights,
        "applied_weights": {name: round(value, 6) for name, value in applied_weights.items()},
        "profile_id": str(profile.id),
        "profile_version": profile.version,
        "warnings": warnings,
        "requires_teacher_review": bool(warnings),
    }
