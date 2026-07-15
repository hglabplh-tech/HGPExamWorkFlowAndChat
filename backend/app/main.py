# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for main."""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import router as api_router
from .chat import router as chat_router
from .config import get_settings
from .database import engine
from .models import Base
from .retention import RETENTION_DDL
from .services.logging_config import configure_logging, current_logging_config, sanitize_mapping

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
settings = get_settings()
configure_logging(settings.log_level, settings.log_file_path, settings.log_debug_values)
logger = logging.getLogger("hgp_exam_workflow.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenient for the starter; replace with Alembic migrations before production.
    """Perform the lifespan operation."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for statement in RETENTION_DDL:
            await connection.execute(text(statement))
    yield
    await engine.dispose()


app = FastAPI(title="HGPExamWorkFlowAndChat API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(chat_router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def log_rest_entry_exit(request: Request, call_next):
    """Log REST entry and exit metadata when INFO logging is enabled."""
    started = time.perf_counter()
    entry = {
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query),
        "client": request.client.host if request.client else None,
    }
    logger.info("rest_entry %s", entry)
    if current_logging_config().get("debug_values"):
        logger.debug("rest_entry_values %s", sanitize_mapping(dict(request.headers)))
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("rest_exception method=%s path=%s", request.method, request.url.path)
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    exit_values = {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }
    logger.info("rest_exit %s", exit_values)
    if current_logging_config().get("debug_values"):
        logger.debug("rest_exit_values %s", sanitize_mapping(dict(response.headers)))
    return response


@app.get("/health")
async def health() -> dict:
    """Perform the health operation."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    """Perform the ready operation."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/", include_in_schema=False)
async def index():
    """Perform the index operation."""
    return FileResponse(FRONTEND / "index.html")


@app.get("/admin", include_in_schema=False)
async def admin():
    """Perform the admin operation."""
    return FileResponse(FRONTEND / "admin.html")
