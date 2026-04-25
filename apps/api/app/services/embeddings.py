"""임베딩 클라이언트 — OpenAI-compatible API 추상화"""

import logging

import tiktoken
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_encoder = tiktoken.get_encoding("cl100k_base")
# 한국어 등 CJK 텍스트는 tiktoken이 실제 임베딩 모델 토큰 수를 과소평가함.
# 실측 비율 상한(~1.71)보다 여유 있게 1.8 적용.
_TIKTOKEN_SAFETY_RATIO = 1.8


class EmbeddingClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
        )
        self._max_tiktoken = int(settings.embedding_max_tokens / _TIKTOKEN_SAFETY_RATIO)

    def _truncate(self, text: str) -> str:
        tokens = _encoder.encode(text)
        if len(tokens) <= self._max_tiktoken:
            return text
        truncated = _encoder.decode(tokens[: self._max_tiktoken])
        logger.warning(
            "임베딩 트런케이션: %d → %d tiktoken 토큰 (embedding_max_tokens=%d)",
            len(tokens),
            self._max_tiktoken,
            settings.embedding_max_tokens,
        )
        return truncated

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트 임베딩 벡터를 반환합니다."""
        response = await self._client.embeddings.create(
            model=settings.embedding_model,
            input=self._truncate(text),
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """다수 텍스트를 배치로 임베딩합니다."""
        if not texts:
            return []

        truncated_texts = [self._truncate(t) for t in texts]

        # 배치 크기 제한 (로컬 모델 OOM 방지)
        batch_size = 32
        all_embeddings: list[list[float]] = []

        for i in range(0, len(truncated_texts), batch_size):
            batch = truncated_texts[i : i + batch_size]
            response = await self._client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings


def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()
