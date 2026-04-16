"""인사말 LLM 자동 번역 서비스

번역 결과는 Redis에 캐싱되므로 동일한 (원문, 언어) 조합은
LLM을 한 번만 호출합니다.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24시간
_LANG_NAMES: dict[str, str] = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "vi": "Vietnamese",
    "th": "Thai",
}


def _cache_key(text: str, lang: str) -> str:
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    return f"greeting:translate:{text_hash}:{lang}"


class GreetingTranslator:
    """LLM을 이용해 greeting을 target_lang으로 번역합니다.

    Redis 캐싱으로 중복 LLM 호출을 방지합니다.
    LLM·Redis 오류 시 원문을 그대로 반환하여 위젯 동작에 영향을 주지 않습니다.
    """

    def __init__(self, redis: Any, llm: Any) -> None:
        self._redis = redis
        self._llm = llm

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> str:
        """greeting text를 target_lang으로 번역합니다.

        Args:
            text: 번역할 원문 인사말.
            target_lang: 목표 언어 코드 (예: "en", "ja").
            source_lang: 원문 언어 코드 (같으면 번역 생략, None이면 항상 번역).

        Returns:
            번역된 인사말. 오류 발생 시 원문 반환.
        """
        if not text:
            return ""

        # 원문과 같은 언어면 번역 불필요
        if source_lang and source_lang.split("-")[0] == target_lang.split("-")[0]:
            return text

        # 캐시 조회
        cached = await self._get_cached(text, target_lang)
        if cached is not None:
            return cached

        # LLM 번역
        try:
            translated = await self._call_llm(text, target_lang)
        except Exception as exc:
            logger.warning("greeting 번역 LLM 오류 — 원문 반환: %s", exc)
            return text

        # 캐시 저장 (오류 무시)
        await self._set_cached(text, target_lang, translated)
        return translated

    async def _get_cached(self, text: str, lang: str) -> str | None:
        try:
            value = await self._redis.get(_cache_key(text, lang))
            return value
        except Exception as exc:
            logger.warning("greeting 번역 캐시 조회 오류: %s", exc)
            return None

    async def _set_cached(self, text: str, lang: str, translated: str) -> None:
        try:
            await self._redis.set(_cache_key(text, lang), translated, ex=_CACHE_TTL)
        except Exception as exc:
            logger.warning("greeting 번역 캐시 저장 오류: %s", exc)

    async def _call_llm(self, text: str, target_lang: str) -> str:
        lang_name = _LANG_NAMES.get(target_lang.split("-")[0], target_lang)
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a translation assistant. "
                    f"Translate the given greeting message into {lang_name} ({target_lang}). "
                    "Output ONLY the translated text — no explanations, no quotes, no extra punctuation."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ]
        result = await self._llm.chat(messages, temperature=0.3, max_tokens=200)
        return result.strip()
