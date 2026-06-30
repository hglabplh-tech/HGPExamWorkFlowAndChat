import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from .database import SessionLocal
from .models import ConversationMember, Message, Submission, User
from .security import decode_user_id


router = APIRouter()


class Rooms:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, set[WebSocket]] = {}

    def disconnect(self, course_id: uuid.UUID, socket: WebSocket) -> None:
        self.connections.get(course_id, set()).discard(socket)

    async def broadcast(self, course_id: uuid.UUID, message: dict) -> None:
        for socket in list(self.connections.get(course_id, set())):
            await socket.send_json(message)


rooms = Rooms()


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_chat(socket: WebSocket, conversation_id: uuid.UUID):
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
                        if shared_type != "submission" or not shared_id:
                            await socket.send_json({"error": "Unsupported shared resource"})
                            continue
                        submission = await db.get(Submission, uuid.UUID(shared_id))
                        if not submission or submission.student_id != user_id or submission.deleted_at:
                            await socket.send_json({"error": "Only your own active submission can be shared"})
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
