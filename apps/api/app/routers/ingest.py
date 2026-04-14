"""문서 인제스트 API"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.document import Document
from app.models.tenant import Tenant
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.ingest import IngestService

settings = get_settings()
router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class URLIngestRequest(BaseModel):
    url: HttpUrl
    title: str | None = None
    crawl_full_site: bool = False


class DocumentResponse(BaseModel):
    id: int
    title: str
    source_type: str
    source_url: str | None
    status: str
    chunk_count: int
    error_message: str | None
    refresh_interval_hours: int
    last_refreshed_at: datetime | None
    next_refresh_at: datetime | None

    model_config = {"from_attributes": True}


@router.post("/url", response_model=DocumentResponse, status_code=202)
async def ingest_url(
    body: URLIngestRequest,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    url_str = str(body.url)
    document = Document(
        tenant_id=tenant.id,
        title=body.title or url_str,
        source_type="url",
        source_url=url_str,
        status="pending",
        refresh_interval_hours=tenant.default_url_refresh_hours,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    await db.commit()  # 백그라운드 태스크의 새 세션에서 document를 조회할 수 있도록 커밋

    background_tasks.add_task(
        _run_url_ingest, document.id, body.crawl_full_site, embedding_client
    )
    return document


@router.post("/file", response_model=DocumentResponse, status_code=202)
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기가 {settings.max_upload_size_mb}MB를 초과합니다.",
        )

    # 파일 저장
    os.makedirs(settings.upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.upload_dir, filename)
    Path(file_path).write_bytes(content)

    source_type = ext.lstrip(".")
    document = Document(
        tenant_id=tenant.id,
        title=file.filename or filename,
        source_type=source_type,
        file_path=file_path,
        status="pending",
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    await db.commit()  # 백그라운드 태스크의 새 세션에서 document를 조회할 수 있도록 커밋

    background_tasks.add_task(_run_file_ingest, document.id, embedding_client)
    return document


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == tenant.id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


class RefreshIntervalRequest(BaseModel):
    refresh_interval_hours: int


@router.post("/documents/{doc_id}/refresh", response_model=DocumentResponse, status_code=202)
async def refresh_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    """URL 문서를 즉시 갱신한다."""
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if doc.source_type != "url":
        raise HTTPException(status_code=400, detail="URL 문서만 갱신할 수 있습니다.")
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="이미 처리 중입니다.")

    await db.execute(
        update(Document).where(Document.id == doc_id).values(status="pending")
    )
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(_run_url_ingest, doc_id, False, embedding_client)
    return doc


@router.patch("/documents/{doc_id}/refresh-interval", response_model=DocumentResponse)
async def update_refresh_interval(
    doc_id: int,
    body: RefreshIntervalRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """URL 문서의 갱신 주기를 변경한다."""
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if doc.source_type != "url":
        raise HTTPException(status_code=400, detail="URL 문서만 갱신 주기를 설정할 수 있습니다.")

    now = datetime.now(timezone.utc)
    interval = body.refresh_interval_hours
    next_refresh = (now + timedelta(hours=interval)) if interval > 0 else None
    await db.execute(
        update(Document)
        .where(Document.id == doc_id)
        .values(refresh_interval_hours=interval, next_refresh_at=next_refresh)
    )
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    await db.delete(doc)
    await db.commit()


async def _run_url_ingest(
    doc_id: int, crawl_full_site: bool, embedding_client: EmbeddingClient
) -> None:
    from app.db.session import AsyncSessionLocal

    logger.info("URL 인제스트 시작: doc_id=%d", doc_id)
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_id)
        if not document:
            logger.warning("URL 인제스트: doc_id=%d 문서 없음", doc_id)
            return
        try:
            # ingest_url 내부에서 db.commit()이 호출되면 document 객체가 expired 되므로
            # 미리 값을 읽어둔다
            interval = document.refresh_interval_hours
            service = IngestService(db=db, embedding_client=embedding_client)
            await service.ingest_url(document, crawl_full_site=crawl_full_site)
            now = datetime.now(timezone.utc)
            next_refresh = (now + timedelta(hours=interval)) if interval > 0 else None
            await db.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(last_refreshed_at=now, next_refresh_at=next_refresh)
            )
            await db.commit()
            logger.info("URL 인제스트 완료: doc_id=%d", doc_id)
        except Exception as exc:
            logger.exception("URL 인제스트 실패: doc_id=%d, error=%s", doc_id, exc)
            # service 내부에서 실패를 기록하지 못했을 경우 최후 수단으로 직접 업데이트
            try:
                await db.execute(
                    update(Document)
                    .where(Document.id == doc_id)
                    .values(status="failed", error_message="인제스트 처리 중 오류가 발생했습니다.")
                )
                await db.commit()
            except Exception:
                logger.exception("URL 인제스트 실패 상태 저장 실패: doc_id=%d", doc_id)


async def _run_file_ingest(doc_id: int, embedding_client: EmbeddingClient) -> None:
    from app.db.session import AsyncSessionLocal

    logger.info("파일 인제스트 시작: doc_id=%d", doc_id)
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_id)
        if not document:
            logger.warning("파일 인제스트: doc_id=%d 문서 없음", doc_id)
            return
        try:
            service = IngestService(db=db, embedding_client=embedding_client)
            await service.ingest_file(document)
            logger.info("파일 인제스트 완료: doc_id=%d", doc_id)
        except Exception as exc:
            logger.exception("파일 인제스트 실패: doc_id=%d, error=%s", doc_id, exc)
            # service 내부에서 실패를 기록하지 못했을 경우 최후 수단으로 직접 업데이트
            try:
                await db.execute(
                    update(Document)
                    .where(Document.id == doc_id)
                    .values(status="failed", error_message="인제스트 처리 중 오류가 발생했습니다.")
                )
                await db.commit()
            except Exception:
                logger.exception("파일 인제스트 실패 상태 저장 실패: doc_id=%d", doc_id)
