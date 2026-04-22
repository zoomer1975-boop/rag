"""Kanana Safeguard — 사용자 입력 안전 검사 클라이언트

kakaocorp/kanana-safeguard-prompt-2.1b 모델을 vLLM OpenAI-compatible API로 호출한다.
출력 레이블:
  <SAFE>       — 안전한 입력
  <UNSAFE-A1>  — Prompt Injection
  <UNSAFE-A2>  — Prompt Leaking
"""

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class SafeguardResult:
    is_safe: bool
    label: str


class SafeguardClient:
    """kanana-safeguard-prompt-2.1b vLLM 서버 클라이언트."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.safeguard_base_url,
            api_key=settings.safeguard_api_key,
        )

    async def check(self, user_message: str) -> SafeguardResult:
        """사용자 메시지의 안전성을 검사한다.

        모델의 chat template이 자동으로 시스템 프롬프트를 추가하므로
        user 메시지만 전달한다.
        """
        try:
            response = await self._client.chat.completions.create(
                model=settings.safeguard_model,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=10,
                temperature=0.0,
            )
            raw = (response.choices[0].message.content or "").strip()
            # "<SAFE>" 포함 + "<UNSAFE>" 미포함 → 안전
            is_safe = "SAFE" in raw and "UNSAFE" not in raw
            label = raw or "UNKNOWN"
            logger.info("[safeguard] label=%r is_safe=%s", label, is_safe)
            return SafeguardResult(is_safe=is_safe, label=label)
        except Exception:
            logger.exception("[safeguard] 서비스 오류")
            # fail_open=True: 장애 시 허용 / False: 장애 시 차단
            return SafeguardResult(
                is_safe=settings.safeguard_fail_open,
                label="ERROR",
            )


def get_safeguard_client() -> SafeguardClient:
    return SafeguardClient()
