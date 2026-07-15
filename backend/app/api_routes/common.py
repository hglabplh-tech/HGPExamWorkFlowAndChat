# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for common."""
import json
import uuid
import asyncio
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Course, Enrollment, ExamGroup, ExamQuestion, Examination, PrivatePKI, Role, Submission, User, UserCertificate
from ..services.asag import grade_answer
from ..services.evidence import certificate_sha256, sha256_hex
from ..services.reports import generate_exam_report
from ..services.authorization import has_permission
from ..services.configuration_cache import CachedScoringProfile, cached_active_scoring_profile
from ..services.grading_scales import convert_grades
from ..services.multiple_choice import score_choice_answer


def require_staff(user: User) -> None:
    """Perform the require staff operation."""
    if not has_permission(user, "content.manage") and user.role != Role.teacher:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff permission required")


def require_admin(user: User) -> None:
    """Perform the require admin operation."""
    if not has_permission(user, "users.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator permission required")


def require_training_manager(user: User) -> None:
    """Perform the require training manager operation."""
    if not has_permission(user, "training.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Training-data manager permission required")


async def require_course_access(db: AsyncSession, user: User, course_id: uuid.UUID) -> None:
    """Perform the require course access operation."""
    if user.role in {Role.staff, Role.admin}:
        return
    membership = await db.scalar(select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == user.id,
    ))
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Course enrollment required")


async def require_course_instructor(db: AsyncSession, user: User, course_id: uuid.UUID) -> None:
    """Perform the require course instructor operation."""
    if user.role in {Role.staff, Role.admin}:
        return
    membership = await db.scalar(select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == user.id,
        Enrollment.role == Role.teacher,
    ))
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Course instructor permission required")


async def require_active_signing_certificate(db: AsyncSession, user: User, fingerprint: str) -> None:
    """Perform the require active signing certificate operation."""
    certificate = await db.scalar(select(UserCertificate).join(
        PrivatePKI, PrivatePKI.id == UserCertificate.private_pki_id,
    ).where(
        UserCertificate.user_id == user.id,
        UserCertificate.sha256_fingerprint == fingerprint,
        UserCertificate.revoked.is_(False),
        PrivatePKI.enabled.is_(True),
    ))
    if not certificate:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Signing certificate is not active in an enabled application trust chain")


async def active_scoring_profile(db: AsyncSession, course: Course) -> CachedScoringProfile | None:
    """Perform the active scoring profile operation."""
    return await cached_active_scoring_profile(db, course.discipline)


async def build_grade_proposal(db: AsyncSession, submission: Submission) -> dict:
    """Perform the build grade proposal operation."""
    examination = await db.get(Examination, submission.examination_id)
    course = await db.get(Course, examination.course_id) if examination else None
    if not course:
        raise HTTPException(status.HTTP_409_CONFLICT, "Submission has no valid course")
    profile = await active_scoring_profile(db, course)
    if not profile:
        raise HTTPException(status.HTTP_409_CONFLICT, "No active scoring profile exists for this discipline")
    questions = (await db.scalars(select(ExamQuestion).where(
        ExamQuestion.examination_id == examination.id,
    ).order_by(ExamQuestion.id))).all()
    results = []
    for question in questions:
        answer = str(submission.answers.get(str(question.id), ""))
        if question.question_type in {"single_choice", "multiple_choice"}:
            result = score_choice_answer(submission.answers.get(str(question.id), []), question.correct_options, question.max_score, question.partial_credit)
        else:
            result = await asyncio.to_thread(grade_answer, question, answer, profile)
        result["question_id"] = str(question.id)
        results.append(result)
    total = round(sum(result["score"] for result in results), 3)
    maximum = round(sum(result["max_score"] for result in results), 3)
    return {
        "profile_id": str(profile.id),
        "profile_version": profile.version,
        "discipline": profile.discipline,
        "questions": results,
        "total": total,
        "maximum": maximum,
        "grade_conversions": convert_grades(total, maximum),
        "requires_teacher_review": any(result["requires_teacher_review"] for result in results),
        "status": "provisional",
    }


async def store_exam_report(db: AsyncSession, submission: Submission, examination: Examination) -> None:
    """Perform the store exam report operation."""
    course = await db.get(Course, examination.course_id)
    student = await db.get(User, submission.student_id)
    exam_group = await db.get(ExamGroup, submission.exam_group_id) if submission.exam_group_id else None
    questions = (await db.scalars(select(ExamQuestion).where(
        ExamQuestion.examination_id == examination.id,
    ).order_by(ExamQuestion.id))).all()
    effective_grade = submission.teacher_grade if examination.kind == "real" else submission.ai_grade
    scores = effective_grade.get("scores", {}) if effective_grade else {}
    ai_results = {item["question_id"]: item for item in (submission.ai_grade or {}).get("questions", [])}
    question_rows = []
    for question in questions:
        metrics = ai_results.get(str(question.id), {})
        question_rows.append({
            "prompt": question.prompt,
            "answer": str(submission.answers.get(str(question.id), "")),
            "score": float(scores.get(str(question.id), metrics.get("score", 0.0))),
            "max_score": question.max_score,
            "signals": metrics.get("signals", {}),
            "feedback": (
                (effective_grade or {}).get("feedback", "")
                if examination.kind == "real"
                else "; ".join(metrics.get("warnings", [])) or "Automated practice scoring; instructor review was not performed."
            ),
        })
    total = float((effective_grade or {}).get("total", sum(item["score"] for item in question_rows)))
    maximum = float((submission.ai_grade or {}).get("maximum", sum(item["max_score"] for item in question_rows)))
    student_cert_hash = certificate_sha256(submission.student_certificate_pem)
    data = {
        "submission_id": str(submission.id),
        "exam_title": examination.title,
        "exam_kind": examination.kind,
        "student_name": student.display_name,
        "exam_group": f"{exam_group.label}: {exam_group.topic}" if exam_group else None,
        "course_title": f"{course.code} - {course.title}",
        "submitted_at": submission.submitted_at.isoformat(),
        "returned_at": submission.returned_at.isoformat() if submission.returned_at else None,
        "status": submission.state,
        "total_score": total,
        "maximum_score": maximum,
        "questions": question_rows,
        "grade_conversions": convert_grades(total, maximum),
        "academic_integrity_review": submission.academic_integrity_review,
        "exam_sha256": submission.content_sha256,
        "student_certificate_sha256": student_cert_hash,
        "student_signature_sha256": sha256_hex(submission.student_signature),
        "grading_sha256": submission.grading_sha256 or sha256_hex(json.dumps(effective_grade or {}, sort_keys=True, separators=(",", ":")).encode()),
        "instructor_certificate_sha256": certificate_sha256(submission.instructor_certificate_pem) if submission.instructor_certificate_pem else None,
        "instructor_signature_sha256": sha256_hex(submission.instructor_signature) if submission.instructor_signature else None,
        "instructor_signed_at": submission.instructor_signed_at.isoformat() if submission.instructor_signed_at else None,
    }
    report = await asyncio.to_thread(generate_exam_report, data)
    submission.report_pdf = report
    submission.report_sha256 = sha256_hex(report)
    submission.report_generated_at = datetime.now(UTC)
