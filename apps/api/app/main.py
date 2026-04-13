"""FastAPI 애플리케이션 진입점"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import analytics, chat, ingest, tenants

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
