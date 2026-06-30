# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for database."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Perform the get db operation."""
    async with SessionLocal() as session:
        yield session

