"""FastAPI 애플리케이션 진입점"""

import logging
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import analytics, chat, ingest, tenants

settings = get_settings()
logger = logging.getLogger(__name__)

WIDGET_DIR = pathlib.Path(__file__).parent.parent / "static" / "widget"


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    WIDGET_DIR.mkdir(parents=True, exist_ok=True)
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


@app.get("/widget/{filename}")
async def serve_widget(filename: str):
    # path traversal 방지
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = WIDGET_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(file_path))


@app.get("/health")
async def health():
    return {"status": "ok"}
