"""LLM 클라이언트 — OpenAI-compatible API 추상화"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from app.config import get_settings

settings = get_settings()


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
            temperature=temperature or settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ToolCallResult | TextResult:
        """Tool calling 지원 채팅 완성 (non-streaming).

        Returns:
            ToolCallResult: LLM이 tool 호출을 요청한 경우
            TextResult: LLM이 텍스트로 바로 응답한 경우
        """
        response = await self._client.chat.completions.create(
            model=model or settings.llm_model,
            messages=messages,
            tools=tools,
            temperature=temperature or settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message

        if msg.tool_calls:  # finish_reason이 "stop"인 provider도 있으므로 tool_calls 우선 확인
            # tool_calls를 messages에 추가할 수 있는 dict 형태로 변환
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content,
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

        return TextResult(content=msg.content or "")

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 채팅 완성 — 토큰 단위로 yield"""
        stream = await self._client.chat.completions.create(
            model=model or settings.llm_model,
            messages=messages,
            temperature=temperature or settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def get_llm_client() -> LLMClient:
    return LLMClient()
