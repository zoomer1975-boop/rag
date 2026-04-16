"""Chat API — SSE 스트리밍, 다국어, 대화 히스토리"""

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.services.domain_validation import is_origin_allowed
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.language import LanguageService
from app.services.langsmith_logger import LangSmithLogger, create_logger
from app.services.llm import LLMClient, get_llm_client
from app.services.rag import RAGService

settings = get_settings()
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.get("/widget-config")
async def widget_config(
    tenant: Tenant = Depends(get_tenant),
):
    """위젯 설정 조회 — 위젯 초기화 시 호출"""
    config: dict = {
        "primary_color": tenant.widget_config.get("primary_color", "#0066ff"),
        "title": tenant.widget_config.get("title", "챗봇"),
        "greeting": tenant.widget_config.get("greeting", ""),
        "placeholder": tenant.widget_config.get("placeholder", "메시지를 입력하세요..."),
        "position": tenant.widget_config.get("position", "bottom-right"),
        "quick_replies": tenant.widget_config.get("quick_replies", []),
    }
    if icon_url := tenant.widget_config.get("button_icon_url"):
        config["button_icon_url"] = icon_url
    return config


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    accept_language: str | None = Header(None, alias="Accept-Language"),
):
    """SSE 스트리밍 채팅 엔드포인트"""
    # 도메인 화이트리스트 검증
    origin = request.headers.get("origin")
    if not is_origin_allowed(origin, tenant.allowed_domain_list):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 도메인은 위젯 사용이 허용되지 않았습니다.",
        )

    lang_service = LanguageService(default_language=settings.default_language)
    detected_lang = lang_service.parse_accept_language(accept_language)
    resolved_lang = lang_service.resolve_lang(
        detected=detected_lang,
        policy=tenant.lang_policy,
        default_lang=tenant.default_lang,
        allowed_langs=tenant.allowed_lang_list,
    )

    session_id = body.session_id or str(uuid.uuid4())

    # 대화 세션 조회 또는 생성
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

    # 대화 히스토리 로드
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

    # LangSmith 로거 초기화 (키 없으면 no-op)
    ls_logger = create_logger(tenant.langsmith_api_key)
    ls_run_id = ls_logger.start_trace(
        run_name="rag_chat",
        inputs={"query": body.message, "tenant_id": tenant.id, "session_id": session_id},
    )

    # RAG 검색
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

    # 사용자 메시지 저장
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.commit()

    return StreamingResponse(
        _stream_response(
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
            "X-Session-Id": session_id,
            "X-Language": resolved_lang,
        },
    )


async def _stream_response(
    llm_client: LLMClient,
    messages: list[dict],
    sources: list[dict],
    conversation_id: int,
    session_id: str,
    ls_logger: LangSmithLogger,
    ls_run_id: str | None,
) -> AsyncGenerator[str, None]:
    full_response = ""

    # 세션 ID 먼저 전송
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

    # 소스 정보 전송
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    # 토큰 스트리밍
    try:
        async for token in llm_client.chat_stream(messages):
            full_response += token
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as exc:
        ls_logger.end_trace(run_id=ls_run_id, error=str(exc))
        raise

    # 완료 이벤트
    yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

    ls_logger.end_trace(run_id=ls_run_id, outputs={"response": full_response, "sources_count": len(sources)})

    # 응답 저장 (백그라운드)
    await _save_assistant_message(conversation_id, full_response, sources)


async def _save_assistant_message(
    conversation_id: int, content: str, sources: list[dict]
) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            sources=sources,
        )
        db.add(msg)
        await db.commit()
