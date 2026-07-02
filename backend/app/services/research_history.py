# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Research-history utilities for query refinement and user-managed sessions."""
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActiveUserSession, ResearchHistory, ResearchHistoryEntry, User

TOKEN_RE = re.compile(r"[\wÄÖÜäöüß]{4,}", re.UNICODE)


async def current_or_create_history(
    db: AsyncSession,
    user: User,
    session: ActiveUserSession | None,
    *,
    label: str = "New chat",
) -> ResearchHistory:
    """Return the user's active unstored history for this session, creating it when needed."""
    history = None
    if session:
        history = await db.scalar(select(ResearchHistory).where(
            ResearchHistory.user_id == user.id,
            ResearchHistory.active_session_id == session.id,
            ResearchHistory.deleted_at.is_(None),
            ResearchHistory.stored.is_(False),
        ).order_by(ResearchHistory.updated_at.desc()))
    if not history:
        history = ResearchHistory(user_id=user.id, active_session_id=session.id if session else None, label=label)
        db.add(history)
        await db.flush()
    return history


async def recent_entries(db: AsyncSession, history: ResearchHistory, *, limit: int = 8) -> list[ResearchHistoryEntry]:
    """Load the newest entries from one history for lightweight context reuse."""
    return list((await db.scalars(select(ResearchHistoryEntry).where(
        ResearchHistoryEntry.history_id == history.id,
    ).order_by(ResearchHistoryEntry.created_at.desc()).limit(limit))).all())


def refine_query_with_history(query: str, entries: list[ResearchHistoryEntry]) -> str:
    """Expand a query with high-signal terms from recent search and scoring history."""
    existing = {token.casefold() for token in TOKEN_RE.findall(query)}
    additions: list[str] = []
    for entry in entries[:5]:
        source = f"{entry.label or ''} {entry.input_text} {entry.output_summary}"
        for token in TOKEN_RE.findall(source):
            normalized = token.casefold()
            if normalized not in existing and normalized not in additions:
                additions.append(normalized)
            if len(additions) >= 8:
                break
        if len(additions) >= 8:
            break
    if not additions:
        return query
    return f"{query} {' '.join(additions)}"


async def record_history_entry(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveUserSession | None,
    kind: str,
    input_text: str,
    course_id: uuid.UUID | None = None,
    refined_text: str | None = None,
    output_summary: str = "",
    payload: dict | None = None,
    label: str | None = None,
) -> ResearchHistoryEntry:
    """Persist one query/scoring event in the current history."""
    history = await current_or_create_history(db, user, session)
    history.updated_at = datetime.now(UTC)
    entry = ResearchHistoryEntry(
        history_id=history.id,
        user_id=user.id,
        course_id=course_id,
        kind=kind,
        label=label,
        input_text=input_text,
        refined_text=refined_text,
        output_summary=output_summary[:4000],
        payload=payload or {},
    )
    db.add(entry)
    await db.flush()
    return entry


def summarize_hits(results: list) -> str:
    """Build a compact history summary from search-hit style result objects."""
    titles = [getattr(item, "title", "") for item in results[:5]]
    return "; ".join(title for title in titles if title)
