"""Chat API — SSE 스트리밍, 다국어, 대화 히스토리"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.models.tenant_api_tool import TenantApiTool
import redis.asyncio as aioredis

from app.services.clarifier import ClarifierService
from app.services.conv_encryption import get_encryptor
from app.services.domain_validation import is_origin_allowed
from app.services.safeguard import SafeguardClient, get_safeguard_client
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.greeting_translator import GreetingTranslator
from app.services.language import LanguageService
from app.services.langsmith_logger import LangSmithLogger, create_logger
from app.services.llm import LLMClient, TextResult, ToolCallResult, get_llm_client
from app.services.rag import RAGService
from app.services.reranker import RerankerService, get_reranker_service
from app.services.tool_executor import MAX_TOOL_CALLS_PER_CHAT, build_openai_tools, execute_tool

logger = logging.getLogger(__name__)

settings = get_settings()
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(
        None,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    )


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
    safeguard_client: SafeguardClient = Depends(get_safeguard_client),
    reranker: RerankerService | None = Depends(get_reranker_service),
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

    # Safeguard 입력 검사 — 비용이 큰 RAG/LLM 호출 전에 빠르게 차단
    if settings.safeguard_enabled:
        sg_result = await safeguard_client.check(body.message)
        if not sg_result.is_safe:
            logger.warning(
                "[safeguard] BLOCKED tenant_id=%d label=%r msg_preview=%r",
                tenant.id,
                sg_result.label,
                body.message[:80],
            )
            blocked_session_id = body.session_id or str(uuid.uuid4())
            return StreamingResponse(
                _stream_blocked(blocked_session_id, settings.safeguard_blocked_message),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Session-Id": blocked_session_id,
                },
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

    # DEK 조회 (없으면 자동 생성 후 DB에 저장)
    enc = get_encryptor()
    dek = await enc.get_or_create_dek(tenant_id=tenant.id, db=db)

    # 대화 히스토리 로드 + 복호화
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    history_msgs = list(reversed(history_result.scalars().all()))
    history = [
        {
            "role": m.role,
            "content": enc.decrypt(m.content_enc, dek) if m.content_enc else (m.content or ""),
        }
        for m in history_msgs
    ]
    clarification_round = sum(1 for m in history_msgs if m.message_type == "clarification_request")

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
        llm_client=llm_client,
        reranker=reranker,
        reranker_top_n=settings.reranker_top_n,
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

    # 명확화 질문 체크 (테넌트별 옵션)
    if tenant.clarification_enabled:
        clarifier = ClarifierService()
        clarification = await clarifier.should_clarify(
            query=body.message,
            top_score=None,  # GraphRAG는 의미있는 유사도 점수를 제공하지 않음
            context_snippets=[c.get("content", "")[:300] for c in retrieved_chunks[:3]],
            clarification_round=clarification_round,
        )
        if clarification.needs_clarification:
            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=None,
                content_enc=enc.encrypt(body.message, dek),
            )
            db.add(user_msg)
            await db.commit()
            return StreamingResponse(
                _stream_clarification(
                    session_id=session_id,
                    questions=clarification.questions,
                    conversation_id=conversation.id,
                    enc_dek=dek,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Session-Id": session_id,
                    "X-Language": resolved_lang,
                },
            )

    # 사용자 메시지 저장 (암호화)
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=None,
        content_enc=enc.encrypt(body.message, dek),
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
            enc_dek=dek,
            safeguard_client=safeguard_client if settings.safeguard_enabled else None,
            safeguard_blocked_message=settings.safeguard_blocked_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
            "X-Language": resolved_lang,
        },
    )


async def _stream_blocked(session_id: str, message: str) -> AsyncGenerator[str, None]:
    """safeguard 차단 시 고정 메시지를 SSE 형식으로 반환한다."""
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
    yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'content': message})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': message})}\n\n"


async def _stream_clarification(
    session_id: str,
    questions: list[str],
    conversation_id: int,
    enc_dek: bytes | None = None,
) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
    yield f"data: {json.dumps({'type': 'clarification', 'questions': questions})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
    await _save_clarification_message(conversation_id, questions, enc_dek=enc_dek)


async def _save_clarification_message(
    conversation_id: int, questions: list[str], enc_dek: bytes | None = None
) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.conv_encryption import get_encryptor

    try:
        async with AsyncSessionLocal() as db:
            enc = get_encryptor()
            plain = "\n".join(questions)
            content_enc = enc.encrypt(plain, enc_dek) if enc_dek else None
            msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=None if content_enc else plain,
                content_enc=content_enc,
                message_type="clarification_request",
                clarification_meta={"questions": questions},
            )
            db.add(msg)
            await db.commit()
    except Exception as exc:
        logger.warning("명확화 메시지 저장 실패 (conversation_id=%d): %s", conversation_id, exc)


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
    enc_dek: bytes | None = None,
    safeguard_client: SafeguardClient | None = None,
    safeguard_blocked_message: str = "",
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
            any_tool_called = False

            while call_count < MAX_TOOL_CALLS_PER_CHAT:
                result = await llm_client.chat_with_tools(
                    messages=current_messages,
                    tools=openai_tools,
                )

                if isinstance(result, TextResult):
                    if any_tool_called:
                        # 케이스 B: tool history 있음 → chat_stream에 tools 없이 보내면 vLLM 오류
                        # 이미 계산된 content를 단어 단위 fake 스트리밍
                        words = result.content.split(" ")
                        for i, word in enumerate(words):
                            chunk = word + (" " if i < len(words) - 1 else "")
                            full_response += chunk
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                    else:
                        # 케이스 A: tool history 없음 → chat_stream으로 실제 스트리밍 가능
                        async for token in llm_client.chat_stream(current_messages):
                            full_response += token
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    break

                # ToolCallResult — tool 실행
                any_tool_called = True
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

    # LLM 출력 safeguard 검사 — 유해 출력이면 클라이언트에 교체 지시
    if safeguard_client is not None and full_response:
        sg_out = await safeguard_client.check(full_response)
        if not sg_out.is_safe:
            logger.warning(
                "[safeguard] OUTPUT BLOCKED label=%r preview=%r",
                sg_out.label,
                full_response[:80],
            )
            yield f"data: {json.dumps({'type': 'output_blocked', 'content': safeguard_blocked_message})}\n\n"
            await ls_logger.log_llm_end(run_id=ls_llm_run_id, response="", error="output_blocked")
            await ls_logger.end_trace(run_id=ls_run_id, error="output_blocked")
            return

    # 완료 이벤트
    yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"

    await ls_logger.log_llm_end(run_id=ls_llm_run_id, response=full_response)
    await ls_logger.end_trace(run_id=ls_run_id, outputs={"response": full_response, "sources_count": len(sources)})

    # 응답 저장 (백그라운드)
    await _save_assistant_message(conversation_id, full_response, sources, enc_dek=enc_dek)


async def _save_assistant_message(
    conversation_id: int, content: str, sources: list[dict], enc_dek: bytes | None = None
) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.conv_encryption import get_encryptor

    async with AsyncSessionLocal() as db:
        enc = get_encryptor()
        content_enc = enc.encrypt(content, enc_dek) if enc_dek else None
        msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=None if content_enc else content,
            content_enc=content_enc,
            sources=sources,
        )
        db.add(msg)
        await db.commit()
