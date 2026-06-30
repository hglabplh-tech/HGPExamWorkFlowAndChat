"""Exam lifecycle policy independent from HTTP and persistence concerns.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""


class ExamWorkflowPolicy:
    """Validate student and instructor transitions in an exam lifecycle."""

    TRANSITIONS = {
        "draft": {"released"},
        "released": {"submitted"},
        "submitted": {"graded"},
        "graded": {"returned"},
    }

    @classmethod
    def may_transition(cls, current: str, target: str) -> bool:
        """Return whether the requested lifecycle transition is permitted."""
        return target in cls.TRANSITIONS.get(current, set())

    @classmethod
    def require_transition(cls, current: str, target: str) -> None:
        """Raise a clear error when an exam transition is not permitted."""
        if not cls.may_transition(current, target):
            raise ValueError(f"Invalid exam transition: {current} -> {target}")

    @staticmethod
    def feedback_is_immediate(exam_kind: str) -> bool:
        """Return whether AI-only grading may be shown immediately."""
        return exam_kind == "test"
