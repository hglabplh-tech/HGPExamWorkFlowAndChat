# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for audit."""
import hashlib
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent


async def append_audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    reason: str = "",
    details: dict | None = None,
) -> AuditEvent:
    # Serialize writers so two events cannot claim the same previous hash.
    """Perform the append audit operation."""
    await db.execute(text("SELECT pg_advisory_xact_lock(741852963)"))
    previous = await db.scalar(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1))
    material = {
        "actor_id": str(actor_id),
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id),
        "reason": reason,
        "details": details or {},
        "previous": previous.event_hash if previous else None,
    }
    event_hash = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        details=details or {},
        previous_event_hash=previous.event_hash if previous else None,
        event_hash=event_hash,
    )
    db.add(event)
    return event

