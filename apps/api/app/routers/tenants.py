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

# magic bytes → canonical extension mapping (client Content-Type cannot be trusted)
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "webp"),  # WebP starts with RIFF....WEBP; verified below
]


def _detect_image_ext(data: bytes) -> str | None:
    """Return canonical extension if magic bytes match a supported image, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import verify_admin
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.models.tenant_api_tool import TenantApiTool
from app.services.embeddings import get_embedding_client
from app.services.language import LanguageService
from app.services.langsmith_logger import LangSmithLogger, create_logger
from app.services.llm import TextResult, get_llm_client
from app.services.rag import RAGService
from app.services.safeguard import SafeguardClient, get_safeguard_client
from app.services.pii_masker import PIIMasker
from app.services.tool_executor import MAX_TOOL_CALLS_PER_CHAT, build_openai_tools, execute_tool

logger = logging.getLogger(__name__)

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)

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
    pii_config: dict | None = None


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
    pii_config: dict | None = None

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
            pii_config=tenant.pii_config,
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

    contents = await file.read()
    if len(contents) > MAX_ICON_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 2MB를 초과할 수 없습니다.")

    # magic bytes로 실제 이미지 형식 검증 (Content-Type은 클라이언트 제어이므로 신뢰 불가)
    ext = _detect_image_ext(contents)
    if ext is None:
        raise HTTPException(status_code=400, detail="이미지 파일(PNG/JPG/GIF/WebP)만 업로드할 수 있습니다.")

    # 기존 아이콘 파일 삭제
    old_icon_url = tenant.widget_config.get("button_icon_url", "")
    if old_icon_url:
        old_filename = old_icon_url.split("/")[-1]
        old_path = ICONS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    # 새 파일 저장 (magic bytes에서 추출한 ext 사용)
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
    safeguard_client: SafeguardClient = Depends(get_safeguard_client),
    _: None = Depends(verify_admin),
):
    """어드민 전용 채팅 테스트 — 도메인 검증 없이 RAG 채팅을 직접 실행."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    settings = get_settings()

    # Safeguard 입력 검사
    if settings.safeguard_enabled:
        sg_result = await safeguard_client.check(body.message)
        if not sg_result.is_safe:
            logger.warning(
                "[safeguard] BLOCKED (admin-chat-test) tenant_id=%d label=%r msg_preview=%r",
                tenant_id,
                sg_result.label,
                body.message[:80],
            )
            blocked_session_id = body.session_id or str(uuid.uuid4())
            return StreamingResponse(
                _admin_stream_blocked(blocked_session_id, settings.safeguard_blocked_message),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Session-Id": blocked_session_id,
                },
            )
    # PII 마스킹 — safeguard 이후, 임베딩/LLM 이전
    pii_cfg = tenant.pii_config if hasattr(tenant, "pii_config") else {}
    if pii_cfg.get("enabled"):
        _pii_masker = PIIMasker()
        _mask_result = await _pii_masker.mask(
            body.message, enabled_types=pii_cfg.get("types")
        )
        user_message = _mask_result.masked_text
    else:
        user_message = body.message

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
    ls_run_id = await ls_logger.start_trace(
        run_name="admin_rag_chat_test",
        inputs={"query": user_message, "tenant_id": tenant.id, "session_id": session_id},
    )

    tools_result = await db.execute(
        select(TenantApiTool).where(
            TenantApiTool.tenant_id == tenant.id,
            TenantApiTool.is_active == True,  # noqa: E712
        )
    )
    active_tools = tools_result.scalars().all()
    openai_tools = build_openai_tools(list(active_tools))
    logger.info(
        "[tool_calling] tenant_id=%d active_tools=%d openai_tools=%d names=%s",
        tenant.id,
        len(active_tools),
        len(openai_tools),
        [t["function"]["name"] for t in openai_tools],
    )
    tool_map = {t.name: t for t in active_tools}

    rag_service = RAGService(
        db=db,
        embedding_client=embedding_client,
        language_service=lang_service,
    )
    retrieved_chunks = await rag_service.retrieve(
        query=user_message,
        tenant_id=tenant.id,
        top_k=5,
    )
    await ls_logger.log_retrieval(
        parent_run_id=ls_run_id,
        query=user_message,
        chunks=[{"content": c.get("content", ""), "source": c.get("source", "")} for c in retrieved_chunks],
    )

    messages = rag_service.build_messages(
        query=user_message,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history,
        tenant=tenant,
        lang_code=resolved_lang,
        policy=tenant.lang_policy,
        allowed_langs=tenant.allowed_lang_list,
        has_tools=bool(openai_tools),
    )
    sources = rag_service.build_sources(retrieved_chunks)

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_message,
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
            openai_tools=openai_tools,
            tool_map=tool_map,
            safeguard_client=safeguard_client if settings.safeguard_enabled else None,
            safeguard_blocked_message=settings.safeguard_blocked_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


async def _admin_stream_blocked(session_id: str, blocked_message: str) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'content': blocked_message})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': blocked_message})}\n\n"


async def _admin_chat_stream(
    llm_client,
    messages: list[dict],
    sources: list[dict],
    conversation_id: int,
    session_id: str,
    ls_logger: LangSmithLogger,
    ls_run_id: str | None,
    openai_tools: list[dict] | None = None,
    tool_map: dict[str, TenantApiTool] | None = None,
    safeguard_client: SafeguardClient | None = None,
    safeguard_blocked_message: str = "",
) -> AsyncGenerator[str, None]:
    full_response = ""

    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    try:
        if openai_tools:
            call_count = 0
            current_messages = list(messages)
            any_tool_called = False

            while call_count < MAX_TOOL_CALLS_PER_CHAT:
                result = await llm_client.chat_with_tools(
                    messages=current_messages,
                    tools=openai_tools,
                )

                if isinstance(result, TextResult):
                    if any_tool_called:
                        words = result.content.split(" ")
                        for i, word in enumerate(words):
                            chunk = word + (" " if i < len(words) - 1 else "")
                            full_response += chunk
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                    else:
                        async for token in llm_client.chat_stream(current_messages):
                            full_response += token
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    break

                any_tool_called = True
                current_messages.append(result.assistant_message)

                for tc in result.tool_calls:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'arguments': arguments})}\n\n"

                    tool_instance = (tool_map or {}).get(tool_name)
                    if not tool_instance:
                        tool_result_content = f"[Error] Unknown tool: {tool_name}"
                        yield f"data: {json.dumps({'type': 'tool_error', 'name': tool_name, 'error': 'Unknown tool'})}\n\n"
                    else:
                        try:
                            tool_result_content = await execute_tool(tool_instance, arguments)
                            preview = tool_result_content[:200]
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'success': True, 'preview': preview})}\n\n"
                        except Exception as e:
                            tool_result_content = f"[Error] {e}"
                            logger.warning("tool '%s' 실행 실패: %s", tool_name, e)
                            yield f"data: {json.dumps({'type': 'tool_error', 'name': tool_name, 'error': str(e)})}\n\n"

                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result_content,
                    })

                call_count += 1
            else:
                logger.warning("tool calling 최대 횟수(%d) 초과, 강제 종료", MAX_TOOL_CALLS_PER_CHAT)
                full_response = await llm_client.chat(messages=current_messages)
                yield f"data: {json.dumps({'type': 'token', 'content': full_response})}\n\n"

        else:
            async for token in llm_client.chat_stream(messages):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    except Exception as exc:
        await ls_logger.end_trace(run_id=ls_run_id, error=str(exc))
        yield f"data: {json.dumps({'type': 'error', 'content': f'LLM 오류: {exc}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        return

    # LLM 출력 safeguard 검사
    if safeguard_client is not None and full_response:
        sg_out = await safeguard_client.check(full_response)
        if not sg_out.is_safe:
            logger.warning(
                "[safeguard] OUTPUT BLOCKED (admin-chat-test) label=%r preview=%r",
                sg_out.label,
                full_response[:80],
            )
            yield f"data: {json.dumps({'type': 'output_blocked', 'content': safeguard_blocked_message})}\n\n"
            await ls_logger.end_trace(run_id=ls_run_id, error="output_blocked")
            return

    yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

    await ls_logger.end_trace(run_id=ls_run_id, outputs={"response": full_response, "sources_count": len(sources)})

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
