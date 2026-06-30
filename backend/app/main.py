from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import router as api_router
from .chat import router as chat_router
from .database import engine
from .models import Base
from .retention import RETENTION_DDL

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenient for the starter; replace with Alembic migrations before production.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for statement in RETENTION_DDL:
            await connection.execute(text(statement))
    yield
    await engine.dispose()


app = FastAPI(title="Study Platform API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(chat_router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/admin", include_in_schema=False)
async def admin():
    return FileResponse(FRONTEND / "admin.html")
