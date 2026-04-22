"""LLM 클라이언트 — OpenAI-compatible API 추상화"""

import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Gemma4 vLLM thinking 블록 패턴: <|channel>thought\n...\n<channel|>
_THINKING_RE = re.compile(r"<\|channel>thought.*?<channel\|>\s*", re.DOTALL)

# thinking 블록 시작 마커 (스트리밍 감지용)
_THINKING_START = "<|channel>"
_THINKING_END = "<channel|>"


def strip_thinking_tokens(text: str) -> str:
    """Gemma4 vLLM thinking 블록을 제거한다.

    <|channel>thought ... <channel|> 형식의 블록을 제거하고
    실제 응답 텍스트만 반환한다.
    """
    return _THINKING_RE.sub("", text).lstrip("\n")


@dataclass
class ToolCallResult:
    """LLM이 tool 호출을 요청했을 때 반환되는 결과"""
    tool_calls: list[ChatCompletionMessageToolCall]
    assistant_message: dict[str, Any]  # messages에 추가할 assistant role 메시지


@dataclass
class TextResult:
    """LLM이 텍스트 응답을 반환했을 때의 결과"""
    content: str


class LLMClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """일반 채팅 완성 (단일 응답)"""
        response = await self._client.chat.completions.create(
            model=model or settings.llm_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
        )
        content = response.choices[0].message.content or ""
        return strip_thinking_tokens(content)

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ToolCallResult | TextResult:
        """Tool calling 지원 채팅 완성 (non-streaming).

        Gemma4 등 vLLM 모델은 tool calling 시 temperature=0이 필수.
        temperature를 명시하지 않으면 0.0을 사용한다.

        Returns:
            ToolCallResult: LLM이 tool 호출을 요청한 경우
            TextResult: LLM이 텍스트로 바로 응답한 경우
        """
        _model = model or settings.llm_model
        # temperature=0.0은 falsy이므로 `or` 대신 `is not None` 체크
        _temperature = temperature if temperature is not None else 0.0
        logger.info(
            "[tool_calling] REQUEST model=%s tools=%d tool_names=%s temperature=%s",
            _model,
            len(tools),
            [t["function"]["name"] for t in tools if t.get("function")],
            _temperature,
        )

        response = await self._client.chat.completions.create(
            model=_model,
            messages=messages,
            tools=tools,
            temperature=_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message

        logger.info(
            "[tool_calling] RESPONSE finish_reason=%r has_tool_calls=%s content_preview=%r",
            choice.finish_reason,
            bool(msg.tool_calls),
            (msg.content or "")[:120],
        )
        # vLLM 진단: tool call이 content 텍스트 안에 숨어있는지 확인
        if not msg.tool_calls and msg.content and (
            "<tool_call>" in msg.content
            or "```json" in msg.content
            or '"name"' in msg.content
            or "function_call" in msg.content
        ):
            logger.warning(
                "[tool_calling] SUSPECTED_TEXT_TOOL_CALL — vLLM may need "
                "--enable-auto-tool-choice --tool-call-parser <parser>. "
                "content=%r",
                msg.content[:300],
            )

        if msg.tool_calls:  # finish_reason이 "stop"인 provider도 있으므로 tool_calls 우선 확인
            logger.info(
                "[tool_calling] TOOL_CALLS_DETECTED calls=%s",
                [{"name": tc.function.name, "args": tc.function.arguments[:80]} for tc in msg.tool_calls],
            )
            # tool_calls를 messages에 추가할 수 있는 dict 형태로 변환
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            return ToolCallResult(tool_calls=msg.tool_calls, assistant_message=assistant_message)

        return TextResult(content=strip_thinking_tokens(msg.content or ""))

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 채팅 완성 — 토큰 단위로 yield.

        Gemma4 vLLM의 thinking 블록(<|channel>thought...<channel|>)을
        감지해 사용자에게 노출하지 않는다.
        """
        stream = await self._client.chat.completions.create(
            model=model or settings.llm_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
            stream=True,
        )

        # thinking 블록이 스트림 앞부분에 나타나면 버퍼에 모아 두었다가
        # <channel|> 이후부터 yield한다.
        buf = ""
        in_thinking = False
        thinking_done = False

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if not delta:
                continue

            if thinking_done:
                # thinking 제거 완료 — 이후 토큰은 바로 yield
                yield delta
                continue

            buf += delta

            if not in_thinking:
                if _THINKING_START in buf:
                    in_thinking = True
                else:
                    # thinking 마커 없음 — 충분한 버퍼가 쌓일 때까지만 보유하고 나머지는 yield
                    # 마커 길이(10) 미만으로 유지하되, 마커 감지 시를 대비해 최대 길이만큼 버퍼 유지
                    min_buffer_size = len(_THINKING_START)
                    if len(buf) > min_buffer_size:
                        # 마커가 토큰 경계에 걸칠 가능성을 대비해 마커 길이만큼 리저브
                        safe_len = len(buf) - min_buffer_size
                        yield buf[:safe_len]
                        buf = buf[safe_len:]

            if in_thinking and _THINKING_END in buf:
                # thinking 블록 끝 감지 — 이후 텍스트만 추출
                after = buf[buf.index(_THINKING_END) + len(_THINKING_END):]
                after = after.lstrip("\n")
                thinking_done = True
                buf = ""
                if after:
                    yield after

        # 스트림 종료 시 버퍼에 남은 내용 처리
        if buf and not in_thinking:
            yield buf


def get_llm_client() -> LLMClient:
    return LLMClient()
