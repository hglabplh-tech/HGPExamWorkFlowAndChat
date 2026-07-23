"""Backend contracts supporting the user and exam execution masks.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.api_routes.chat import chatbot_question, is_chatbot_command
from backend.app.schemas import MessageCreate, QuestionDraftScore, UserCreate


def test_user_create_accepts_matriculation_number_and_permissions() -> None:
    """The user-definition mask payload maps to the API schema."""
    payload = UserCreate(
        email="student@example.org",
        display_name="Student Example",
        password="a-very-long-password",
        matriculation_number="MAT-2026-001",
        permissions=["email.send"],
    )
    assert payload.matriculation_number == "MAT-2026-001"
    assert payload.permissions == ["email.send"]


def test_question_draft_score_accepts_text_and_choice_answers() -> None:
    """The examination execution mask can score free text and multiple choice."""
    assert QuestionDraftScore(answer="free text answer").answer == "free text answer"
    assert QuestionDraftScore(answer=["A", "C"]).answer == ["A", "C"]


def test_message_create_accepts_attachment_metadata() -> None:
    """The chat mask can send files or audio metadata with a message."""
    message = MessageCreate(body="@chatbot check this", attachments=[{"filename": "essay.txt", "sha256": "abc"}])
    assert message.attachments[0]["filename"] == "essay.txt"


def test_chatbot_command_must_start_message() -> None:
    """Only a leading @chatbot mention invokes hybrid-search chatbot behavior."""
    assert is_chatbot_command("@chatbot research cache locality")
    assert chatbot_question("@chatbot research cache locality") == "research cache locality"
    assert not is_chatbot_command("please ask @chatbot later")
