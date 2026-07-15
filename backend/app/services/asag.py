# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for asag."""
import math
import re
import uuid
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ..config import get_settings
from ..models import DisciplineScoringProfile, ExamQuestion
from .bm25 import BM25Document, bm25_rank
from .embeddings import encode
from .model_router import resolve_torch_device

TOKEN = re.compile(r"\w+", re.UNICODE)
ASAG_FORMULA_WEIGHTS = {
    "cross_encoder": 0.40,
    "embedding_similarity": 0.30,
    "jaccard": 0.10,
    "bm25": 0.10,
    "context_match": 0.05,
    "fact_coverage": 0.05,
}
ASAG_WEIGHT_KEYS = set(ASAG_FORMULA_WEIGHTS)


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


def bm25_keyword_coverage(answer: str, keywords: list[str]) -> float | None:
    """Score required keyword coverage with BM25-backed lexical matching."""
    if not keywords:
        return None
    documents = [
        BM25Document(id=uuid.uuid5(uuid.NAMESPACE_URL, f"asag-keyword:{index}:{keyword}"), title=keyword, text=keyword)
        for index, keyword in enumerate(keywords)
    ]
    hits = bm25_rank(answer, documents, limit=len(documents))
    matched = {hit.title.casefold() for hit in hits if hit.score > 0}
    return sum(keyword.casefold() in matched for keyword in keywords) / len(keywords)


def semantic_similarity(answer: str, reference: str, profile: str) -> float:
    """Perform the semantic similarity operation."""
    vectors = encode(profile, [answer, reference], get_settings().compute_device)
    cosine = sum(left * right for left, right in zip(vectors[0], vectors[1]))
    return max(0.0, min(1.0, cosine))


def embedding_similarity(answer: str, reference: str, profile: str) -> float:
    """Score answer/reference similarity with the configured embedding model."""
    return semantic_similarity(answer, reference, profile)


def length_adequacy(answer: str, reference: str) -> float:
    """Perform the length adequacy operation."""
    reference_length = max(1, len(TOKEN.findall(reference)))
    return min(1.0, len(TOKEN.findall(answer)) / reference_length)


@lru_cache(maxsize=3)
def bert_cross_encoder_components(model_path: str):
    """Load an approved BERT-style cross-encoder from a trained local model path."""
    device = resolve_torch_device(get_settings().compute_device)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path).to(device).eval()
    return tokenizer, model, device


def discipline_slug(value: str) -> str:
    """Perform the discipline slug operation."""
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "general"


def bert_cross_encoder_similarity(reference: str, answer: str, discipline: str) -> float | None:
    """Score answer/reference fit with a local BERT cross-encoder when available."""
    current = Path(get_settings().model_output_dir) / "answer_scoring" / discipline_slug(discipline) / "current"
    if not current.exists():
        return None
    tokenizer, model, device = bert_cross_encoder_components(str(current.resolve()))
    values = tokenizer(reference, answer, return_tensors="pt", truncation=True, max_length=512)
    values = {key: value.to(device) for key, value in values.items()}
    with torch.inference_mode():
        logits = model(**values).logits[0]
    if logits.numel() == 1:
        value = float(torch.sigmoid(logits[0]))
    else:
        value = float(logits.softmax(dim=-1)[-1])
    return max(0.0, min(1.0, value))


def trained_scoring(reference: str, answer: str, discipline: str) -> float | None:
    """Backward-compatible alias for the BERT cross-encoder ASAG score."""
    return bert_cross_encoder_similarity(reference, answer, discipline)


@lru_cache(maxsize=1)
def nli_components():
    """Perform the nli components operation."""
    model_name = get_settings().nli_model
    get_settings().require_allowed_model(model_name)
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


def reference_fact_coverage(answer: str, facts: list[str]) -> float | None:
    """Score how many reference facts are explicitly covered by the answer."""
    if not facts:
        return None
    normalized_answer = " ".join(TOKEN.findall(answer.casefold()))
    covered = 0
    for fact in facts:
        fact_tokens = TOKEN.findall(fact.casefold())
        if not fact_tokens:
            continue
        fact_terms = set(fact_tokens)
        answer_terms = set(TOKEN.findall(normalized_answer))
        overlap = len(fact_terms & answer_terms) / len(fact_terms)
        if overlap >= 0.60:
            covered += 1
    return covered / len(facts)


def hybrid_context_match(answer: str, contexts: list[str], profile: str) -> float | None:
    """Score how well the answer matches retrieved hybrid-search context."""
    if not contexts:
        return None
    return max(embedding_similarity(answer, context, profile) for context in contexts)


def normalize_asag_weights(weights: dict[str, float]) -> dict[str, float]:
    """Return ASAG weights normalized to sum to one."""
    if set(weights) != ASAG_WEIGHT_KEYS:
        raise ValueError("ASAG weights must contain exactly the supported scoring components")
    if any(value < 0 for value in weights.values()):
        raise ValueError("ASAG weights cannot be negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("ASAG weights must contain a positive total")
    return {name: value / total for name, value in weights.items()}


def merge_asag_weight_overrides(overrides: dict[str, float]) -> dict[str, float]:
    """Merge explicit overrides with global defaults without changing explicit values."""
    if not set(overrides) <= ASAG_WEIGHT_KEYS:
        raise ValueError("ASAG weight overrides contain unsupported components")
    explicit = {key: float(value) for key, value in overrides.items()}
    if any(value < 0 for value in explicit.values()) or sum(explicit.values()) > 1:
        raise ValueError("ASAG weight overrides must be non-negative and sum to at most one")
    missing = ASAG_WEIGHT_KEYS - set(explicit)
    remaining = 1.0 - sum(explicit.values())
    default_missing_total = sum(ASAG_FORMULA_WEIGHTS[key] for key in missing)
    merged = dict(explicit)
    for key in missing:
        merged[key] = 0.0 if default_missing_total <= 0 else remaining * ASAG_FORMULA_WEIGHTS[key] / default_missing_total
    return normalize_asag_weights(merged)


def resolve_asag_weights(profile: DisciplineScoringProfile | None, topic: str | None = None) -> dict[str, float]:
    """Resolve topic, discipline, or global ASAG weights.

    Supported ``grading_weights`` formats:
    - flat component mapping for a discipline-wide override;
    - ``{"default": {...}, "topics": {"topic name": {...}}}`` for topic overrides.
    Missing or invalid values fall back to the global formula defaults.
    """
    raw = profile.grading_weights if profile is not None else None
    candidate: dict | None = None
    if isinstance(raw, dict):
        topics = raw.get("topics")
        if topic and isinstance(topics, dict) and isinstance(topics.get(topic), dict):
            candidate = topics[topic]
        elif isinstance(raw.get("default"), dict):
            candidate = raw["default"]
        elif ASAG_WEIGHT_KEYS <= set(raw):
            candidate = raw
    if not candidate:
        return dict(ASAG_FORMULA_WEIGHTS)
    try:
        return merge_asag_weight_overrides({key: float(candidate[key]) for key in ASAG_WEIGHT_KEYS if key in candidate})
    except (TypeError, ValueError):
        return dict(ASAG_FORMULA_WEIGHTS)


def fixed_asag_score(
    signals: dict[str, float | None],
    weights: dict[str, float] | None = None,
) -> tuple[float, dict[str, float], list[str]]:
    """Apply the configured ASAG formula for answer scoring."""
    warnings: list[str] = []
    applied_weights = normalize_asag_weights(weights or ASAG_FORMULA_WEIGHTS)
    score = 0.0
    for name, weight in ASAG_FORMULA_WEIGHTS.items():
        value = signals.get(name)
        if value is None:
            warnings.append(f"ASAG signal unavailable and scored as 0: {name}")
            value = 0.0
        score += weight * value
    return max(0.0, min(1.0, score)), applied_weights, warnings


def grade_answer(
    question: ExamQuestion,
    answer: str,
    profile: DisciplineScoringProfile,
    context_documents: list[str] | None = None,
    topic: str | None = None,
) -> dict:
    """Grade an answer with configured BERT/embedding/lexical/context ASAG weights."""
    contexts = context_documents if context_documents is not None else [question.reference_answer]
    signals: dict[str, float | None] = {
        "cross_encoder": bert_cross_encoder_similarity(question.reference_answer, answer, profile.discipline),
        "embedding_similarity": embedding_similarity(answer, question.reference_answer, profile.semantic_profile),
        "jaccard": jaccard(answer, question.reference_answer),
        "bm25": bm25_keyword_coverage(answer, question.required_keywords),
        "context_match": hybrid_context_match(answer, contexts, profile.semantic_profile),
        "fact_coverage": reference_fact_coverage(answer, question.expected_facts),
    }
    warnings: list[str] = []
    if signals["cross_encoder"] is None:
        warnings.append("No approved BERT cross-encoder scoring model is active; cross_encoder contributes 0")
    try:
        fact_signal = fact_entailment(answer, question.expected_facts)
        if fact_signal is not None:
            signals["fact_coverage"] = fact_signal
        _, contradiction = nli_probabilities(question.reference_answer, answer)
        signals["contradiction_safety"] = 1.0 - contradiction
    except Exception as error:
        warnings.append(f"NLI fact-check signal unavailable: {type(error).__name__}")

    resolved_weights = resolve_asag_weights(profile, topic)
    normalized, applied_weights, formula_warnings = fixed_asag_score(signals, resolved_weights)
    warnings.extend(formula_warnings)
    available = {name: value for name, value in signals.items() if value is not None}
    spread = math.sqrt(sum((value - normalized) ** 2 for value in available.values()) / len(available)) if available else 0.0
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
