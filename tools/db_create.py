# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Small wrapper for creating the database schema and Playground data."""
import asyncio

from backend.app.db_cli import create_schema, init_playground


async def main() -> None:
    """Create tables, apply migrations, and initialize Playground."""
    await create_schema()
    await init_playground()


if __name__ == "__main__":
    asyncio.run(main())
