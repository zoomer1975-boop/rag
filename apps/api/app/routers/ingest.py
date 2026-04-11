"""문서 인제스트 API"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.document import Document
from app.models.tenant import Tenant
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.ingest import IngestService

settings = get_settings()
router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


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
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

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


async def _run_url_ingest(
    doc_id: int, crawl_full_site: bool, embedding_client: EmbeddingClient
) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_id)
        if not document:
            return
        service = IngestService(db=db, embedding_client=embedding_client)
        await service.ingest_url(document, crawl_full_site=crawl_full_site)
        await db.commit()


async def _run_file_ingest(doc_id: int, embedding_client: EmbeddingClient) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_id)
        if not document:
            return
        service = IngestService(db=db, embedding_client=embedding_client)
        await service.ingest_file(document)
        await db.commit()
