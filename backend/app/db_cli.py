# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Database CLI for schema creation and Playground initialization."""
import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select, text

from .database import SessionLocal, engine
from .models import Base, Course, CourseKnowledgeBase
from .retention import RETENTION_DDL

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "infra" / "migrations"


async def create_schema(apply_sql_migrations: bool = True) -> None:
    """Create ORM tables and optionally apply idempotent SQL migrations."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for statement in RETENTION_DDL:
            await connection.execute(text(statement))
        if apply_sql_migrations and MIGRATIONS.exists():
            for path in sorted(MIGRATIONS.glob("*.sql")):
                sql = path.read_text(encoding="utf-8")
                for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                    await connection.execute(text(statement))


async def init_playground() -> None:
    """Create the Playground course and its default PostgreSQL knowledge-base entry."""
    async with SessionLocal() as db:
        course = await db.scalar(select(Course).where(Course.code == "PLAYGROUND"))
        if not course:
            course = Course(
                code="PLAYGROUND",
                title="Playground",
                discipline="Playground",
                description="Experimental course for ASAG, ASR, RAG, hybrid-search, and model-training trials.",
            )
            db.add(course)
            await db.flush()
        kb = await db.scalar(select(CourseKnowledgeBase).where(
            CourseKnowledgeBase.course_id == course.id,
            CourseKnowledgeBase.name == "default",
        ))
        if not kb:
            db.add(CourseKnowledgeBase(
                course_id=course.id,
                name="default",
                description="Default Playground entry point for PostgreSQL full-text, BM25, and mBERT/semantic search.",
                fulltext_config="simple",
                semantic_profile="economy",
                active=True,
                settings={"source": "db_cli"},
            ))
        await db.commit()
        print(f"Initialized Playground course: {course.id}")


async def main() -> None:
    """Run the selected database CLI command."""
    parser = argparse.ArgumentParser(description="HGPExamWorkFlowAndChat database CLI")
    parser.add_argument("command", choices=["create-schema", "init-playground", "bootstrap-playground"])
    parser.add_argument("--skip-sql-migrations", action="store_true")
    args = parser.parse_args()
    if args.command == "create-schema":
        await create_schema(apply_sql_migrations=not args.skip_sql_migrations)
        print("Database schema created")
    elif args.command == "init-playground":
        await init_playground()
    else:
        await create_schema(apply_sql_migrations=not args.skip_sql_migrations)
        await init_playground()


if __name__ == "__main__":
    asyncio.run(main())
