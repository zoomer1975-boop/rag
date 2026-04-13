"""FastAPI 애플리케이션 진입점"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import analytics, chat, ingest, tenants

settings = get_settings()
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Alembic 마이그레이션을 시작 시 자동으로 실행합니다."""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("DB 마이그레이션 완료")
    except Exception:
        logger.exception("DB 마이그레이션 실패 — 수동으로 확인하세요")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_migrations)
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs("./static/widget", exist_ok=True)
    yield


app = FastAPI(
    title="RAG Chatbot API",
    version="1.0.0",
    root_path=settings.app_prefix,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenants.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(analytics.router)

widget_dir = "./static/widget"
os.makedirs(widget_dir, exist_ok=True)
app.mount("/widget", StaticFiles(directory=widget_dir), name="widget")


@app.get("/health")
async def health():
    return {"status": "ok"}
