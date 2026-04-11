"""임베딩 클라이언트 — OpenAI-compatible API 추상화"""

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()


class EmbeddingClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
        )

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트 임베딩 벡터를 반환합니다."""
        response = await self._client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """다수 텍스트를 배치로 임베딩합니다."""
        if not texts:
            return []

        # 배치 크기 제한 (로컬 모델 OOM 방지)
        batch_size = 32
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await self._client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings


def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()
