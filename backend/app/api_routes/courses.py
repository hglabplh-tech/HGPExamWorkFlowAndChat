# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for courses."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Course, DisciplineScoringProfile, ModelTrainingRun, TrainingExample, User
from ..schemas import CourseCreate, CourseOut, ScoringProfileCreate, TrainingApproval
from ..security import authenticate, require_nonce
from ..services.audit import append_audit
from ..services.configuration_cache import invalidate_configuration


from .common import (
    require_admin, require_training_manager,
)

router = APIRouter(prefix="/api/v1")


@router.post("/training/start", status_code=202)
async def start_training(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Request an immediate audited training run without waiting for the scheduler."""
    require_training_manager(user)
    running = await db.scalar(select(ModelTrainingRun).where(ModelTrainingRun.status == "running"))
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "A model training run is already active")
    from backend.training_job import run

    background.add_task(run)
    await append_audit(db, user.id, "training_start_requested", "training", user.id)
    await db.commit()
    return {"status": "accepted", "execution": "background", "requested_by": user.id}

@router.get("/courses", response_model=list[CourseOut])
async def courses(db: AsyncSession = Depends(get_db), _: User = Depends(authenticate)):
    """Perform the courses operation."""
    return (await db.scalars(select(Course).order_by(Course.code))).all()


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(data: CourseCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create course operation."""
    require_training_manager(user)
    item = Course(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/scoring-profiles", status_code=201)
async def create_scoring_profile(data: ScoringProfileCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create scoring profile operation."""
    require_admin(user)
    try:
        data.validate_weights()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    version = (await db.scalar(select(func.max(DisciplineScoringProfile.version)).where(
        DisciplineScoringProfile.discipline == data.discipline,
    ))) or 0
    await db.execute(update(DisciplineScoringProfile).where(
        DisciplineScoringProfile.discipline == data.discipline,
        DisciplineScoringProfile.active.is_(True),
    ).values(active=False))
    profile = DisciplineScoringProfile(
        discipline=data.discipline,
        version=version + 1,
        grading_weights=data.grading_weights,
        search_weights=data.search_weights,
        semantic_profile=data.semantic_profile,
        created_by=user.id,
    )
    db.add(profile)
    await db.flush()
    await append_audit(db, user.id, "scoring_profile_created", "discipline_scoring_profile", profile.id, details={"discipline": profile.discipline, "version": profile.version, "grading_weights": profile.grading_weights, "search_weights": profile.search_weights})
    await db.commit()
    invalidate_configuration("scoring", data.discipline)
    return {"id": profile.id, "discipline": profile.discipline, "version": profile.version}


@router.get("/scoring-profiles")
async def scoring_profiles(discipline: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the scoring profiles operation."""
    require_admin(user)
    query = select(DisciplineScoringProfile).order_by(DisciplineScoringProfile.discipline, DisciplineScoringProfile.version.desc())
    if discipline:
        query = query.where(DisciplineScoringProfile.discipline == discipline)
    items = (await db.scalars(query)).all()
    return [{"id": item.id, "discipline": item.discipline, "version": item.version, "active": item.active, "grading_weights": item.grading_weights, "search_weights": item.search_weights, "semantic_profile": item.semantic_profile} for item in items]


@router.get("/training/examples")
async def training_examples(
    approved: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the training examples operation."""
    require_training_manager(user)
    query = select(TrainingExample).order_by(TrainingExample.created_at.desc()).limit(limit)
    if approved is not None:
        query = query.where(TrainingExample.approved.is_(approved))
    items = (await db.scalars(query)).all()
    return [{"id": item.id, "task": item.task, "discipline": item.discipline, "payload": item.payload, "approved": item.approved, "created_at": item.created_at} for item in items]


@router.post("/training/examples/{example_id}/decision")
async def decide_training_example(
    example_id: uuid.UUID,
    data: TrainingApproval,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the decide training example operation."""
    require_training_manager(user)
    item = await db.get(TrainingExample, example_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Training example not found")
    item.approved = data.approved
    item.approved_by = user.id if data.approved else None
    await append_audit(db, user.id, "training_example_approved" if data.approved else "training_example_rejected", "training_example", item.id, data.reason)
    await db.commit()
    return {"id": item.id, "approved": item.approved}


@router.get("/training/runs")
async def training_runs(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the training runs operation."""
    require_training_manager(user)
    items = (await db.scalars(select(ModelTrainingRun).order_by(ModelTrainingRun.started_at.desc()).limit(100))).all()
    return [{"id": item.id, "task": item.task, "discipline": item.discipline, "status": item.status, "example_count": item.example_count, "artifact_path": item.artifact_path, "metrics": item.metrics, "started_at": item.started_at, "finished_at": item.finished_at} for item in items]
