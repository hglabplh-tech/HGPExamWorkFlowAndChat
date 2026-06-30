import math
import re
from functools import lru_cache

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ..config import get_settings
from ..models import DisciplineScoringProfile, ExamQuestion
from .embeddings import encode
from .model_router import resolve_torch_device

TOKEN = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN.findall(text)}


def jaccard(answer: str, reference: str) -> float:
    left, right = tokens(answer), tokens(reference)
    return len(left & right) / len(left | right) if left or right else 1.0


def keyword_coverage(answer: str, keywords: list[str]) -> float | None:
    if not keywords:
        return None
    normalized = " ".join(TOKEN.findall(answer.casefold()))
    return sum(" ".join(TOKEN.findall(keyword.casefold())) in normalized for keyword in keywords) / len(keywords)


def semantic_similarity(answer: str, reference: str, profile: str) -> float:
    vectors = encode(profile, [answer, reference], get_settings().compute_device)
    cosine = sum(left * right for left, right in zip(vectors[0], vectors[1]))
    return max(0.0, min(1.0, cosine))


def length_adequacy(answer: str, reference: str) -> float:
    reference_length = max(1, len(TOKEN.findall(reference)))
    return min(1.0, len(TOKEN.findall(answer)) / reference_length)


@lru_cache(maxsize=1)
def nli_components():
    model_name = get_settings().nli_model
    device = resolve_torch_device(get_settings().compute_device)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device).eval()
    labels = {index: label.lower() for index, label in model.config.id2label.items()}
    entailment = next(index for index, label in labels.items() if "entail" in label)
    contradiction = next(index for index, label in labels.items() if "contrad" in label)
    return tokenizer, model, device, entailment, contradiction


def nli_probabilities(premise: str, hypothesis: str) -> tuple[float, float]:
    tokenizer, model, device, entailment, contradiction = nli_components()
    values = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)
    values = {key: value.to(device) for key, value in values.items()}
    with torch.inference_mode():
        probabilities = model(**values).logits.softmax(dim=-1)[0]
    return float(probabilities[entailment]), float(probabilities[contradiction])


def fact_entailment(answer: str, facts: list[str]) -> float | None:
    if not facts:
        return None
    # The student's answer is the premise; each teacher-approved fact is a hypothesis.
    return sum(nli_probabilities(answer, fact)[0] for fact in facts) / len(facts)


def grade_answer(question: ExamQuestion, answer: str, profile: DisciplineScoringProfile) -> dict:
    signals: dict[str, float | None] = {
        "jaccard": jaccard(answer, question.reference_answer),
        "keywords": keyword_coverage(answer, question.required_keywords),
        "semantic": semantic_similarity(answer, question.reference_answer, profile.semantic_profile),
        "fact_entailment": None,
        "contradiction": None,
        "length": length_adequacy(answer, question.reference_answer),
    }
    warnings: list[str] = []
    try:
        signals["fact_entailment"] = fact_entailment(answer, question.expected_facts)
        _, contradiction = nli_probabilities(question.reference_answer, answer)
        signals["contradiction"] = 1.0 - contradiction
    except Exception as error:
        warnings.append(f"NLI fact-check signal unavailable: {type(error).__name__}")

    available = {name: value for name, value in signals.items() if value is not None}
    denominator = sum(profile.grading_weights[name] for name in available)
    if denominator <= 0:
        warnings.append("Configured weights do not cover available signals; equal fallback weights applied")
        applied_weights = {name: 1.0 / len(available) for name in available}
    else:
        applied_weights = {name: profile.grading_weights[name] / denominator for name in available}
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
