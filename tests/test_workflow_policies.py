"""Unit tests for exam and chat policies.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid

import pytest

from backend.app.workflows import ChatVisibilityPolicy, ExamWorkflowPolicy


def test_exam_lifecycle_allows_only_forward_transitions() -> None:
    """The lifecycle prevents skipping or reversing legally relevant states."""
    assert ExamWorkflowPolicy.may_transition("draft", "released")
    assert not ExamWorkflowPolicy.may_transition("released", "returned")
    with pytest.raises(ValueError):
        ExamWorkflowPolicy.require_transition("graded", "submitted")
    assert ExamWorkflowPolicy.feedback_is_immediate("test")
    assert not ExamWorkflowPolicy.feedback_is_immediate("real")


def test_visibility_covers_private_direct_group_and_public_items() -> None:
    """Only intended recipients or group members can read restricted content."""
    owner, recipient, member, stranger = (uuid.uuid4() for _ in range(4))
    assert ChatVisibilityPolicy.can_read("private", owner, owner)
    assert ChatVisibilityPolicy.can_read("direct", recipient, owner, recipient)
    assert ChatVisibilityPolicy.can_read("group", member, owner, member_ids={member})
    assert ChatVisibilityPolicy.can_read("public", stranger, owner)
    assert not ChatVisibilityPolicy.can_read("direct", stranger, owner, recipient)
