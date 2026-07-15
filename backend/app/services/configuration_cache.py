# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Lazy configuration cache with explicit invalidation hooks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import DisciplineScoringProfile, MailServerSettings


@dataclass(frozen=True)
class CacheEntry:
    """Store one cached configuration value with its load timestamp."""
    value: Any
    loaded_at: datetime


@dataclass(frozen=True)
class CachedMailSettings:
    """Detached snapshot of administrator-managed mail settings."""
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_starttls: bool
    smtp_ssl: bool
    email_from: str | None
    support_email: str | None
    imap_host: str | None
    imap_port: int
    imap_username: str | None
    imap_password: str | None
    imap_ssl: bool
    active: bool


@dataclass(frozen=True)
class CachedScoringProfile:
    """Detached snapshot of the active discipline scoring/search configuration."""
    id: UUID
    discipline: str
    version: int
    grading_weights: dict
    search_weights: dict
    semantic_profile: str
    active: bool


_cache: dict[tuple[str, str], CacheEntry] = {}
_versions: dict[str, int] = {"global": 0, "mail": 0, "scoring": 0, "logging": 0}


def _key(section: str, name: str = "default") -> tuple[str, str]:
    """Return the stable cache key for a configuration section."""
    return (section, name)


def cache_status() -> dict[str, Any]:
    """Return lightweight cache diagnostics for administrators and tests."""
    return {
        "versions": dict(_versions),
        "entries": [
            {"section": section, "name": name, "loaded_at": entry.loaded_at.isoformat()}
            for (section, name), entry in sorted(_cache.items())
        ],
    }


def invalidate_configuration(section: str | None = None, name: str | None = None) -> None:
    """Invalidate one configuration section or the complete configuration cache."""
    if section is None:
        _cache.clear()
        for known_section in _versions:
            _versions[known_section] += 1
        get_settings.cache_clear()
        return
    if name is None:
        for cache_key in [cache_key for cache_key in _cache if cache_key[0] == section]:
            _cache.pop(cache_key, None)
    else:
        _cache.pop(_key(section, name), None)
    _versions[section] = _versions.get(section, 0) + 1
    if section == "global":
        get_settings.cache_clear()


def cached_global_settings() -> Any:
    """Return process-global environment settings from the lru-backed settings cache."""
    return get_settings()


def _mail_snapshot(settings: MailServerSettings) -> CachedMailSettings:
    """Detach a mail-settings ORM row into a cache-safe value object."""
    return CachedMailSettings(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_username=settings.smtp_username,
        smtp_password=settings.smtp_password,
        smtp_starttls=settings.smtp_starttls,
        smtp_ssl=settings.smtp_ssl,
        email_from=settings.email_from,
        support_email=settings.support_email,
        imap_host=settings.imap_host,
        imap_port=settings.imap_port,
        imap_username=settings.imap_username,
        imap_password=settings.imap_password,
        imap_ssl=settings.imap_ssl,
        active=settings.active,
    )


async def cached_mail_settings(db: AsyncSession, include_inactive: bool = True) -> CachedMailSettings | None:
    """Return cached default mail settings, reloading lazily after invalidation."""
    cache_name = "default:include_inactive" if include_inactive else "default:active"
    cache_key = _key("mail", cache_name)
    if cache_key in _cache:
        return _cache[cache_key].value
    query = select(MailServerSettings).where(MailServerSettings.name == "default")
    if not include_inactive:
        query = query.where(MailServerSettings.active.is_(True))
    settings = await db.scalar(query)
    snapshot = _mail_snapshot(settings) if settings else None
    _cache[cache_key] = CacheEntry(snapshot, datetime.utcnow())
    return snapshot


def _scoring_snapshot(profile: DisciplineScoringProfile) -> CachedScoringProfile:
    """Detach a scoring-profile ORM row into a cache-safe value object."""
    return CachedScoringProfile(
        id=profile.id,
        discipline=profile.discipline,
        version=profile.version,
        grading_weights=dict(profile.grading_weights or {}),
        search_weights=dict(profile.search_weights or {}),
        semantic_profile=profile.semantic_profile,
        active=profile.active,
    )


async def cached_active_scoring_profile(db: AsyncSession, discipline: str) -> CachedScoringProfile | None:
    """Return the cached active scoring profile for a discipline."""
    cache_key = _key("scoring", discipline)
    if cache_key in _cache:
        return _cache[cache_key].value
    profile = await db.scalar(select(DisciplineScoringProfile).where(
        DisciplineScoringProfile.discipline == discipline,
        DisciplineScoringProfile.active.is_(True),
    ).order_by(DisciplineScoringProfile.version.desc()))
    snapshot = _scoring_snapshot(profile) if profile else None
    _cache[cache_key] = CacheEntry(snapshot, datetime.utcnow())
    return snapshot
