"""문서 인제스트 파이프라인 — 파싱 → 청킹 → 임베딩 → 저장"""

import os
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chunker import TextChunker
from app.services.crawler import WebCrawler
from app.services.embeddings import EmbeddingClient
from app.services.parser import DocumentParser

settings = get_settings()


class IngestService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_client: EmbeddingClient,
        chunker: TextChunker | None = None,
        parser: DocumentParser | None = None,
        crawler: WebCrawler | None = None,
    ) -> None:
        self._db = db
        self._embedding_client = embedding_client
        self._chunker = chunker or TextChunker()
        self._parser = parser or DocumentParser()
        self._crawler = crawler or WebCrawler()

    async def ingest_url(self, document: Document, crawl_full_site: bool = False) -> None:
        """URL을 크롤링하여 청킹 + 임베딩 후 저장합니다."""
        await self._set_status(document, "processing")
        try:
            if crawl_full_site:
                pages = await self._crawler.crawl_site(document.source_url)
            else:
                page = await self._crawler.crawl_url(document.source_url)
                pages = [page]

            total_chunks = 0
            for page in pages:
                chunks_data = self._chunker.split_with_metadata(
                    page["content"],
                    source_url=page["url"],
                    title=page.get("title", ""),
                )
                await self._save_chunks(document, chunks_data)
                total_chunks += len(chunks_data)

            await self._set_status(document, "completed", chunk_count=total_chunks)
        except Exception as exc:
            await self._set_status(document, "failed", error=str(exc))
            raise

    async def ingest_file(self, document: Document) -> None:
        """업로드된 파일을 파싱하여 청킹 + 임베딩 후 저장합니다."""
        await self._set_status(document, "processing")
        try:
            text = self._parser.parse(document.file_path, document.source_type)
            chunks_data = self._chunker.split_with_metadata(
                text,
                source_url=document.source_url,
                title=document.title,
            )
            await self._save_chunks(document, chunks_data)
            await self._set_status(document, "completed", chunk_count=len(chunks_data))
        except Exception as exc:
            await self._set_status(document, "failed", error=str(exc))
            raise

    async def _save_chunks(self, document: Document, chunks_data: list[dict]) -> None:
        if not chunks_data:
            return

        texts = [c["content"] for c in chunks_data]
        embeddings = await self._embedding_client.embed_batch(texts)

        chunks = [
            Chunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                content=data["content"],
                embedding=embedding,
                chunk_index=data["index"],
                chunk_metadata={
                    k: v for k, v in data.items() if k not in ("content", "index")
                },
            )
            for data, embedding in zip(chunks_data, embeddings)
        ]
        self._db.add_all(chunks)
        await self._db.flush()

    async def _set_status(
        self,
        document: Document,
        status: str,
        chunk_count: int = 0,
        error: str | None = None,
    ) -> None:
        document.status = status
        if chunk_count:
            document.chunk_count = chunk_count
        if error:
            document.error_message = error[:1000]
        await self._db.commit()
