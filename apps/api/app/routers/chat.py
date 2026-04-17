"""Chat API — SSE 스트리밍, 다국어, 대화 히스토리"""

import json
import logging
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
from app.models.tenant_api_tool import TenantApiTool
import redis.asyncio as aioredis

from app.services.domain_validation import is_origin_allowed
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.greeting_translator import GreetingTranslator
from app.services.language import LanguageService
from app.services.langsmith_logger import LangSmithLogger, create_logger
from app.services.llm import LLMClient, TextResult, ToolCallResult, get_llm_client
from app.services.rag import RAGService
from app.services.tool_executor import MAX_TOOL_CALLS_PER_CHAT, build_openai_tools, execute_tool

logger = logging.getLogger(__name__)

settings = get_settings()
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.get("/widget-config")
async def widget_config(
    tenant: Tenant = Depends(get_tenant),
    accept_language: str | None = Header(None, alias="Accept-Language"),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """위젯 설정 조회 — 위젯 초기화 시 호출.

    Accept-Language로 브라우저 언어를 감지하여 greeting을 LLM으로 자동 번역합니다.
    번역 결과는 Redis에 24시간 캐싱되어 LLM 호출은 최초 1회만 발생합니다.
    """
    lang_service = LanguageService(default_language=settings.default_language)
    detected_lang = lang_service.parse_accept_language(accept_language)
    resolved_lang = lang_service.resolve_lang(
        detected=detected_lang,
        policy=tenant.lang_policy,
        default_lang=tenant.default_lang,
        allowed_langs=tenant.allowed_lang_list,
    )

    raw_greeting = tenant.widget_config.get("greeting", "")

    # 원문 언어와 다를 때만 LLM 번역 (같으면 즉시 반환)
    if raw_greeting and resolved_lang != tenant.default_lang:
        try:
            redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            translator = GreetingTranslator(redis=redis, llm=llm_client)
            localized_greeting = await translator.translate(
                text=raw_greeting,
                target_lang=resolved_lang,
                source_lang=tenant.default_lang,
            )
        except Exception:
            localized_greeting = raw_greeting
    else:
        localized_greeting = raw_greeting

    config: dict = {
        "primary_color": tenant.widget_config.get("primary_color", "#0066ff"),
        "title": tenant.widget_config.get("title", "챗봇"),
        "greeting": localized_greeting,
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
    ls_logger = create_logger(tenant.langsmith_api_key, tenant.name)
    ls_run_id = await ls_logger.start_trace(
        run_name="rag_chat",
        inputs={"query": body.message, "tenant_id": tenant.id, "session_id": session_id},
    )

    # 활성 API Tools 조회
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
    await ls_logger.log_retrieval(
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
        has_tools=bool(openai_tools),
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

    ls_llm_run_id = await ls_logger.log_llm_start(parent_run_id=ls_run_id, messages=messages)

    # tool_name -> TenantApiTool 매핑 (실행 시 빠른 조회)
    tool_map = {t.name: t for t in active_tools}

    return StreamingResponse(
        _stream_response(
            llm_client=llm_client,
            messages=messages,
            sources=sources,
            conversation_id=conversation.id,
            session_id=session_id,
            ls_logger=ls_logger,
            ls_run_id=ls_run_id,
            ls_llm_run_id=ls_llm_run_id,
            openai_tools=openai_tools,
            tool_map=tool_map,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
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
    ls_llm_run_id: str | None,
    openai_tools: list[dict] | None = None,
    tool_map: dict[str, TenantApiTool] | None = None,
) -> AsyncGenerator[str, None]:
    full_response = ""

    # 세션 ID 먼저 전송
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

    # 소스 정보 전송
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    try:
        # tool이 있으면 tool calling 루프 실행
        if openai_tools:
            call_count = 0
            current_messages = list(messages)

            while call_count < MAX_TOOL_CALLS_PER_CHAT:
                result = await llm_client.chat_with_tools(
                    messages=current_messages,
                    tools=openai_tools,
                )

                if isinstance(result, TextResult):
                    # LLM이 이미 최종 답변을 생성했으므로 재호출 없이 단어 단위 fake 스트리밍
                    # (chat_stream에 tools 없이 tool history를 보내면 vLLM/Ollama 오류 발생)
                    words = result.content.split(" ")
                    for i, word in enumerate(words):
                        chunk = word + (" " if i < len(words) - 1 else "")
                        full_response += chunk
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                    break

                # ToolCallResult — tool 실행
                current_messages.append(result.assistant_message)

                for tc in result.tool_calls:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    # tool_call 이벤트 전송
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'arguments': arguments})}\n\n"

                    tool_instance = tool_map.get(tool_name)
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

                    # tool 결과를 messages에 추가
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result_content,
                    })

                call_count += 1

            else:
                # 최대 횟수 초과 — tool history가 있는 messages를 tools 없이 chat_stream에
                # 보내면 vLLM/Ollama 오류 발생하므로 안정적인 chat()으로 최종 응답 요청
                logger.warning("tool calling 최대 횟수(%d) 초과, 강제 종료", MAX_TOOL_CALLS_PER_CHAT)
                full_response = await llm_client.chat(messages=current_messages)
                yield f"data: {json.dumps({'type': 'token', 'content': full_response})}\n\n"

        else:
            # tool 없는 테넌트 — 기존 스트리밍 흐름 유지
            async for token in llm_client.chat_stream(messages):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    except Exception as exc:
        await ls_logger.log_llm_end(run_id=ls_llm_run_id, response="", error=str(exc))
        await ls_logger.end_trace(run_id=ls_run_id, error=str(exc))
        raise

    # 완료 이벤트
    yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

    await ls_logger.log_llm_end(run_id=ls_llm_run_id, response=full_response)
    await ls_logger.end_trace(run_id=ls_run_id, outputs={"response": full_response, "sources_count": len(sources)})

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
