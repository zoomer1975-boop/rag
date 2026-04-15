"""RAG 파이프라인 — 검색 + 프롬프트 조립"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.tenant import Tenant
from app.services.embeddings import EmbeddingClient
from app.services.language import LanguageService

SYSTEM_PROMPT_TEMPLATE = """You are a helpful assistant for {tenant_name}.
Use the following context to answer the user's question accurately.
If the answer is not in the context, say so honestly — do not make up information.

{lang_instruction}

Context:
{context}
"""


class RAGService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_client: EmbeddingClient,
        language_service: LanguageService,
    ) -> None:
        self._db = db
        self._embedding_client = embedding_client
        self._language_service = language_service

    async def retrieve(
        self,
        query: str,
        tenant_id: int,
        top_k: int = 5,
    ) -> list[dict]:
        """쿼리와 유사한 청크를 테넌트 격리 하에 검색합니다."""
        query_embedding = await self._embedding_client.embed(query)

        # pgvector cosine similarity 검색 (tenant_id 필터로 격리 보장)
        result = await self._db.execute(
            text(
                """
                SELECT id, content, chunk_metadata,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM chunks
                WHERE tenant_id = :tenant_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
                """
            ),
            {
                "embedding": str(query_embedding),
                "tenant_id": tenant_id,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        return [
            {
                "id": row.id,
                "content": row.content,
                "metadata": row.chunk_metadata,
                "score": float(row.score),
            }
            for row in rows
        ]

    def build_messages(
        self,
        query: str,
        retrieved_chunks: list[dict],
        conversation_history: list[dict],
        tenant: Tenant,
        lang_code: str,
        policy: str = "fixed",
        allowed_langs: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """LLM에 전달할 메시지 목록을 조립합니다."""
        lang_instruction = self._language_service.build_lang_instruction(
            lang_code,
            policy=policy,
            allowed_langs=allowed_langs,
        )

        context = "\n\n---\n\n".join(
            f"[Source {i + 1}]\n{chunk['content']}"
            for i, chunk in enumerate(retrieved_chunks)
        )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tenant_name=tenant.name,
            lang_instruction=lang_instruction,
            context=context if context else "No relevant documents found.",
        )

        # 테넌트 커스텀 시스템 프롬프트 추가
        if tenant.system_prompt:
            system_prompt = f"{tenant.system_prompt}\n\n{system_prompt}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        # 대화 히스토리 (최근 10턴)
        for msg in conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": query})
        return messages

    def build_sources(self, retrieved_chunks: list[dict]) -> list[dict]:
        """응답에 포함할 소스 인용 정보를 생성합니다."""
        return [
            {
                "chunk_id": chunk["id"],
                "score": round(chunk["score"], 4),
                "source_url": chunk["metadata"].get("source_url"),
                "title": chunk["metadata"].get("title"),
                "preview": chunk["content"][:200],
            }
            for chunk in retrieved_chunks
            if chunk["score"] > 0.3
        ]
