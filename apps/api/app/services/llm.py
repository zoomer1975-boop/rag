"""LLM 클라이언트 — OpenAI-compatible API 추상화"""

from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()


class LLMClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
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

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
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
