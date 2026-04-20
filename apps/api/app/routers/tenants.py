"""테넌트 관리 API"""

import json
import pathlib
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ICONS_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "icons"
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_ICON_SIZE = 2 * 1024 * 1024  # 2MB

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import verify_admin
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.services.embeddings import get_embedding_client
from app.services.language import LanguageService
from app.services.langsmith_logger import LangSmithLogger, create_logger
from app.services.llm import get_llm_client
from app.services.rag import RAGService

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

MAX_DOMAINS_PER_TENANT = 50


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    system_prompt: str | None = None
    lang_policy: str = "auto"
    default_lang: str = "ko"
    allowed_langs: str = "ko,en,ja,zh"
    allowed_domains: str = ""
    widget_config: dict = Field(default_factory=dict)
    langsmith_api_key: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    system_prompt: str | None = None
    lang_policy: str | None = None
    default_lang: str | None = None
    allowed_langs: str | None = None
    allowed_domains: str | None = None
    widget_config: dict | None = None
    is_active: bool | None = None
    default_url_refresh_hours: int | None = Field(None, ge=0, le=8760)  # 0 = 비활성, 최대 1년
    langsmith_api_key: str | None = None
    clarification_enabled: bool | None = None
    clarification_config: dict | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    api_key: str
    is_active: bool
    lang_policy: str
    default_lang: str
    allowed_langs: str
    allowed_domains: str
    widget_config: dict
    system_prompt: str | None
    default_url_refresh_hours: int
    has_langsmith: bool = False
    clarification_enabled: bool = False
    clarification_config: dict | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_tenant(cls, tenant: "Tenant") -> "TenantResponse":
        return cls(
            id=tenant.id,
            name=tenant.name,
            api_key=tenant.api_key,
            is_active=tenant.is_active,
            lang_policy=tenant.lang_policy,
            default_lang=tenant.default_lang,
            allowed_langs=tenant.allowed_langs,
            allowed_domains=tenant.allowed_domains,
            widget_config=tenant.widget_config,
            system_prompt=tenant.system_prompt,
            default_url_refresh_hours=tenant.default_url_refresh_hours,
            has_langsmith=bool(tenant.langsmith_api_key),
            clarification_enabled=tenant.clarification_enabled,
            clarification_config=tenant.clarification_config,
        )


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return [TenantResponse.from_tenant(t) for t in result.scalars().all()]


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    default_widget = {
        "primary_color": "#0066ff",
        "greeting": "안녕하세요! 무엇을 도와드릴까요?",
        "position": "bottom-right",
        "title": "챗봇",
        "placeholder": "메시지를 입력하세요...",
    }
    widget_config = {**default_widget, **body.widget_config}

    tenant = Tenant(
        name=body.name,
        api_key=Tenant.generate_api_key(),
        system_prompt=body.system_prompt,
        lang_policy=body.lang_policy,
        default_lang=body.default_lang,
        allowed_langs=body.allowed_langs,
        allowed_domains=body.allowed_domains,
        widget_config=widget_config,
        langsmith_api_key=body.langsmith_api_key,
    )
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return TenantResponse.from_tenant(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    return TenantResponse.from_tenant(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    update_data = body.model_dump(exclude_none=True)
    new_interval = update_data.get("default_url_refresh_hours")

    for field, value in update_data.items():
        setattr(tenant, field, value)

    # 갱신 주기가 변경된 경우 기존 URL 문서 전체에 반영
    if new_interval is not None:
        now = datetime.now(timezone.utc)
        next_refresh = (now + timedelta(hours=new_interval)) if new_interval > 0 else None
        await db.execute(
            update(Document)
            .where(Document.tenant_id == tenant_id, Document.source_type == "url")
            .values(
                refresh_interval_hours=new_interval,
                next_refresh_at=next_refresh,
            )
        )

    await db.flush()
    await db.refresh(tenant)
    return TenantResponse.from_tenant(tenant)


@router.post("/{tenant_id}/rotate-key", response_model=TenantResponse)
async def rotate_api_key(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    tenant.api_key = Tenant.generate_api_key()
    await db.flush()
    await db.refresh(tenant)
    return TenantResponse.from_tenant(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    await db.delete(tenant)
    await db.commit()


class DomainAdd(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)


@router.post("/{tenant_id}/domains", response_model=TenantResponse)
async def add_domain(
    tenant_id: int,
    body: DomainAdd,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """도메인 화이트리스트에 도메인 추가"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    domains = tenant.allowed_domain_list
    domain = body.domain.strip().lower()
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="유효하지 않은 도메인 형식입니다.")
    if domain in domains:
        return TenantResponse.from_tenant(tenant)  # already present — idempotent
    if len(domains) >= MAX_DOMAINS_PER_TENANT:
        raise HTTPException(status_code=400, detail=f"도메인은 최대 {MAX_DOMAINS_PER_TENANT}개까지 등록할 수 있습니다.")

    domains.append(domain)
    tenant.allowed_domains = ",".join(domains)
    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return TenantResponse.from_tenant(tenant)


@router.post("/{tenant_id}/icon", response_model=TenantResponse)
async def upload_icon(
    tenant_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """위젯 버튼 아이콘 이미지 업로드"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="이미지 파일(PNG/JPG/GIF/WebP)만 업로드할 수 있습니다.")

    contents = await file.read()
    if len(contents) > MAX_ICON_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 2MB를 초과할 수 없습니다.")

    # 기존 아이콘 파일 삭제
    old_icon_url = tenant.widget_config.get("button_icon_url", "")
    if old_icon_url:
        old_filename = old_icon_url.split("/")[-1]
        old_path = ICONS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    # 새 파일 저장
    ext = (file.filename or "image").rsplit(".", 1)[-1].lower()
    if ext not in {"png", "jpg", "jpeg", "gif", "webp"}:
        ext = "png"
    filename = f"tenant_{tenant_id}_{uuid.uuid4().hex}.{ext}"
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    (ICONS_DIR / filename).write_bytes(contents)

    # widget_config 업데이트 (JSONB mutation 감지를 위해 새 dict 할당)
    icon_url = f"/rag/static/icons/{filename}"
    tenant.widget_config = {**tenant.widget_config, "button_icon_url": icon_url}

    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return TenantResponse.from_tenant(tenant)


@router.delete("/{tenant_id}/icon", response_model=TenantResponse)
async def delete_icon(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """위젯 버튼 아이콘 제거 (기본 SVG로 리셋)"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    old_icon_url = tenant.widget_config.get("button_icon_url", "")
    if old_icon_url:
        old_filename = old_icon_url.split("/")[-1]
        old_path = ICONS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    tenant.widget_config = {k: v for k, v in tenant.widget_config.items() if k != "button_icon_url"}

    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return TenantResponse.from_tenant(tenant)


@router.delete("/{tenant_id}/domains/{domain_index}", response_model=TenantResponse)
async def remove_domain(
    tenant_id: int,
    domain_index: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """도메인 화이트리스트에서 도메인 제거 (0-based index)"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    domains = tenant.allowed_domain_list
    if domain_index < 0 or domain_index >= len(domains):
        raise HTTPException(status_code=400, detail="유효하지 않은 도메인 인덱스입니다.")

    domains.pop(domain_index)
    tenant.allowed_domains = ",".join(domains)
    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return TenantResponse.from_tenant(tenant)


# ─── 어드민 채팅 테스트 ───────────────────────────────────────────────────────


class AdminChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/{tenant_id}/chat-test")
async def admin_chat_test(
    tenant_id: int,
    body: AdminChatRequest,
    db: AsyncSession = Depends(get_db),
    llm_client=Depends(get_llm_client),
    embedding_client=Depends(get_embedding_client),
    _: None = Depends(verify_admin),
):
    """어드민 전용 채팅 테스트 — 도메인 검증 없이 RAG 채팅을 직접 실행."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    settings = get_settings()
    lang_service = LanguageService(default_language=settings.default_language)
    resolved_lang = lang_service.resolve_lang(
        detected=settings.default_language,
        policy=tenant.lang_policy,
        default_lang=tenant.default_lang,
        allowed_langs=tenant.allowed_lang_list,
    )

    session_id = body.session_id or str(uuid.uuid4())

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.session_id == session_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        conversation = Conversation(
            tenant_id=tenant.id,
            session_id=session_id,
            lang_code=resolved_lang,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_result.scalars().all())
    ]

    ls_logger = create_logger(tenant.langsmith_api_key, tenant.name)
    ls_run_id = ls_logger.start_trace(
        run_name="admin_rag_chat_test",
        inputs={"query": body.message, "tenant_id": tenant.id, "session_id": session_id},
    )

    rag_service = RAGService(
        db=db,
        embedding_client=embedding_client,
        language_service=lang_service,
    )
    retrieved_chunks = await rag_service.retrieve(
        query=body.message,
        tenant_id=tenant.id,
        top_k=5,
    )
    ls_logger.log_retrieval(
        parent_run_id=ls_run_id,
        query=body.message,
        chunks=[{"content": c.get("content", ""), "source": c.get("source", "")} for c in retrieved_chunks],
    )

    messages = rag_service.build_messages(
        query=body.message,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history,
        tenant=tenant,
        lang_code=resolved_lang,
        policy=tenant.lang_policy,
        allowed_langs=tenant.allowed_lang_list,
    )
    sources = rag_service.build_sources(retrieved_chunks)

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.commit()

    return StreamingResponse(
        _admin_chat_stream(
            llm_client=llm_client,
            messages=messages,
            sources=sources,
            conversation_id=conversation.id,
            session_id=session_id,
            ls_logger=ls_logger,
            ls_run_id=ls_run_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


async def _admin_chat_stream(
    llm_client,
    messages: list[dict],
    sources: list[dict],
    conversation_id: int,
    session_id: str,
    ls_logger: LangSmithLogger,
    ls_run_id: str | None,
) -> AsyncGenerator[str, None]:
    full_response = ""

    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    try:
        async for token in llm_client.chat_stream(messages):
            full_response += token
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as exc:
        ls_logger.end_trace(run_id=ls_run_id, error=str(exc))
        raise

    yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

    ls_logger.end_trace(run_id=ls_run_id, outputs={"response": full_response, "sources_count": len(sources)})

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as save_db:
        msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            sources=sources,
        )
        save_db.add(msg)
        await save_db.commit()
