"""FastAPI 애플리케이션 진입점"""

import logging
import os
import pathlib
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import admin, analytics, api_tools, auth, boilerplate, chat, ingest, tenants
from app.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
logger = logging.getLogger(__name__)

WIDGET_DIR = pathlib.Path(__file__).parent.parent / "static" / "widget"
ICONS_DIR = pathlib.Path(__file__).parent.parent / "static" / "icons"


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    WIDGET_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="RAG Chatbot API",
    version="1.0.0",
    root_path=settings.app_prefix,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Admin-Token"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(tenants.router)
app.include_router(api_tools.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(boilerplate.router)


@app.get("/widget/{filename}")
async def serve_widget(filename: str):
    # path traversal 방지
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = WIDGET_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(file_path))


@app.get("/static/icons/{filename}")
@app.get("/rag/static/icons/{filename}")  # nginx 없이 직접 접근 시 사용
async def serve_icon(filename: str):
    # path traversal 방지
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = ICONS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(file_path))


@app.get("/health")
async def health():
    return {"status": "ok"}
