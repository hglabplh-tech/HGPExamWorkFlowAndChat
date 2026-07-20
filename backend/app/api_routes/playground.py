# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Playground RPC-over-HTTP endpoints for ASAG scoring experiments."""
import asyncio
import math
import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import DisciplineScoringProfile, ExamQuestion, TrainingExample, User
from ..schemas import PlaygroundAsagScoreRequest, PlaygroundMetricsRequest
from ..security import require_nonce
from ..services.asag import ASAG_FORMULA_WEIGHTS, grade_answer, resolve_asag_weights

router = APIRouter(prefix="/api/v1")

PLAYGROUND_COURSE = {
    "code": "PLAYGROUND",
    "title": "Playground",
    "discipline": "Playground",
    "description": "Experimental course for ASAG, ASR, RAG, and model-training trials.",
}


@router.get("/playground/course")
async def playground_course(_: User = Depends(require_nonce)):
    """Return the built-in playground course/discipline descriptor."""
    return {
        **PLAYGROUND_COURSE,
        "training_candidate_default": True,
        "default_asag_weights": ASAG_FORMULA_WEIGHTS,
        "purpose": "Experiment with request-level scoring weights before promoting settings per discipline/topic.",
    }


def playground_profile(data: PlaygroundAsagScoreRequest) -> DisciplineScoringProfile:
    """Build an in-memory scoring profile from request overrides."""
    config = data.config
    weights = config.weights or dict(ASAG_FORMULA_WEIGHTS)
    return DisciplineScoringProfile(
        discipline=config.discipline or "Playground",
        version=1,
        semantic_profile=config.semantic_profile,
        grading_weights={
            "default": weights,
            "topics": {config.topic: weights} if config.topic else {},
        },
        search_weights={"full_text": 0.35, "bm25": 0.20, "semantic": 0.45},
    )


def playground_question(data: PlaygroundAsagScoreRequest) -> ExamQuestion:
    """Build an in-memory exam question from playground request data."""
    return ExamQuestion(
        prompt=data.prompt,
        reference_answer=data.reference_answer,
        required_keywords=data.required_keywords,
        expected_facts=data.expected_facts,
        max_score=data.max_score,
    )


@router.post("/playground/asag-score")
async def playground_asag_score(
    data: PlaygroundAsagScoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Run one ASAG playground trial with request-level configuration overrides."""
    started = time.perf_counter()
    profile = playground_profile(data)
    question = playground_question(data)
    result = await asyncio.to_thread(
        grade_answer,
        question,
        data.answer,
        profile,
        data.config.context_documents,
        data.config.topic,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    resolved_weights = resolve_asag_weights(profile, data.config.topic)
    trial_id = uuid.uuid4()
    if data.training_candidate:
        db.add(TrainingExample(
            source_type="playground",
            source_id=trial_id,
            task="answer_scoring",
            discipline=data.config.discipline,
            payload={
                "prompt": data.prompt,
                "reference_answer": data.reference_answer,
                "answer": data.answer,
                "required_keywords": data.required_keywords,
                "expected_facts": data.expected_facts,
                "expected_score": data.expected_score,
                "config": data.config.model_dump(),
                "resolved_weights": resolved_weights,
                "result": result,
                "latency_ms": latency_ms,
            },
            approved=False,
        ))
        await db.commit()
    return {
        "trial_id": trial_id,
        "course": PLAYGROUND_COURSE,
        "topic": data.config.topic,
        "training_candidate": data.training_candidate,
        "resolved_weights": resolved_weights,
        "latency_ms": latency_ms,
        "result": result,
    }


@router.post("/playground/asag-metrics")
async def playground_asag_metrics(data: PlaygroundMetricsRequest, _: User = Depends(require_nonce)):
    """Evaluate empirical playground trials for accuracy and latency."""
    errors = [trial.observed_score - trial.expected_score for trial in data.trials]
    absolute_errors = [abs(value) for value in errors]
    within_tolerance = [value <= data.tolerance for value in absolute_errors]
    accuracy = sum(within_tolerance) / len(within_tolerance)
    mae = sum(absolute_errors) / len(absolute_errors)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    average_latency = sum(trial.latency_ms for trial in data.trials) / len(data.trials)
    return {
        "trial_count": len(data.trials),
        "tolerance": data.tolerance,
        "accuracy_within_tolerance": round(accuracy, 6),
        "mean_absolute_error": round(mae, 6),
        "root_mean_square_error": round(rmse, 6),
        "average_latency_ms": round(average_latency, 3),
        "better_than_baseline": None if data.baseline_accuracy is None else accuracy > data.baseline_accuracy,
        "performance_metrics": {
            "max_absolute_error": round(max(absolute_errors), 6),
            "min_absolute_error": round(min(absolute_errors), 6),
            "latency_target_ms": 500,
            "latency_target_met": average_latency <= 500,
        },
    }
