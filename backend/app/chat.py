# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for chat."""
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from .database import SessionLocal
from .models import ConversationMember, Examination, Message, ResearchInteraction, Submission, User
from .security import decode_user_id


router = APIRouter()


class Rooms:
    """Represent rooms."""
    def __init__(self) -> None:
        """Perform the init operation."""
        self.connections: dict[uuid.UUID, set[WebSocket]] = {}

    def disconnect(self, course_id: uuid.UUID, socket: WebSocket) -> None:
        """Perform the disconnect operation."""
        self.connections.get(course_id, set()).discard(socket)

    async def broadcast(self, course_id: uuid.UUID, message: dict) -> None:
        """Perform the broadcast operation."""
        for socket in list(self.connections.get(course_id, set())):
            await socket.send_json(message)


rooms = Rooms()


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_chat(socket: WebSocket, conversation_id: uuid.UUID):
    """Perform the conversation chat operation."""
    await socket.accept()
    try:
        authentication = await socket.receive_json()
        user_id = decode_user_id(str(authentication.get("token", "")))
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            membership = await db.scalar(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.user_id == user_id,
                )
            )
            if not user or not membership:
                await socket.close(code=1008, reason="Conversation membership required")
                return
        rooms.connections.setdefault(conversation_id, set()).add(socket)
        while True:
            message = await socket.receive_json()
            body = str(message.get("body", "")).strip()[:4000]
            shared_type = message.get("shared_type")
            shared_id = message.get("shared_id")
            if body or (shared_type and shared_id):
                async with SessionLocal() as db:
                    if shared_type:
                        resource_id = uuid.UUID(shared_id) if shared_id else None
                        if shared_type == "research_result" and resource_id:
                            research = await db.get(ResearchInteraction, resource_id)
                            if not research or research.user_id != user_id:
                                await socket.send_json({"error": "Only your own research result can be shared"})
                                continue
                            research.visibility = "conversation"
                            research.conversation_id = conversation_id
                        elif shared_type == "practice_score" and resource_id:
                            submission = await db.get(Submission, resource_id)
                            examination = await db.get(Examination, submission.examination_id) if submission else None
                            if not submission or submission.student_id != user_id or submission.deleted_at or not examination or examination.kind != "practice" or not submission.ai_grade:
                                await socket.send_json({"error": "Only your own scored practice examination can be shared"})
                                continue
                        else:
                            await socket.send_json({"error": "Unsupported shared resource"})
                            continue
                    db.add(Message(
                        conversation_id=conversation_id,
                        sender_id=user_id,
                        body=body,
                        shared_type=str(shared_type)[:40] if shared_type else None,
                        shared_id=uuid.UUID(shared_id) if shared_id else None,
                    ))
                    await db.commit()
                await rooms.broadcast(conversation_id, {
                    "body": body,
                    "sender": user.display_name,
                    "shared_type": shared_type,
                    "shared_id": shared_id,
                })
    except (WebSocketDisconnect, ValueError):
        rooms.disconnect(conversation_id, socket)
