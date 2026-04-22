"""문서 인제스트 파이프라인 — 파싱 → 청킹 → 임베딩 → 저장"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services import boilerplate as boilerplate_svc
from app.services.chunker import TextChunker
from app.services.crawler import WebCrawler
from app.services.embeddings import EmbeddingClient
from app.services.parser import DocumentParser
from app.services.security import chunk_sanitizer, content_inspector
from app.services.security.types import Action

settings = get_settings()


class IngestService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_client: EmbeddingClient,
        chunker: TextChunker | None = None,
        parser: DocumentParser | None = None,
        crawler: WebCrawler | None = None,
        graph_extractor: Any | None = None,
        graph_store: Any | None = None,
    ) -> None:
        self._db = db
        self._embedding_client = embedding_client
        self._chunker = chunker or TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self._parser = parser or DocumentParser()
        self._crawler = crawler or WebCrawler()
        self._graph_extractor = graph_extractor
        self._graph_store = graph_store

    async def ingest_url(self, document: Document, crawl_full_site: bool = False) -> None:
        """URL을 크롤링하여 청킹 + 임베딩 후 저장합니다."""
        await self._set_status(document, "processing")
        # 갱신 시 기존 청크 삭제
        await self._db.execute(
            delete(Chunk).where(Chunk.document_id == document.id)
        )
        await self._db.flush()
        try:
            if crawl_full_site:
                pages = await self._crawler.crawl_site(document.source_url)
            else:
                page = await self._crawler.crawl_url(document.source_url)
                pages = [page]

            patterns = await boilerplate_svc.load_patterns(self._db, document.tenant_id)

            total_chunks = 0
            for page in pages:
                content = boilerplate_svc.apply(page["content"], patterns)
                if not content:
                    logger.warning(
                        "보일러플레이트 제거 후 본문이 비었습니다: doc_id=%d, url=%s",
                        document.id,
                        page.get("url"),
                    )
                report = content_inspector.inspect(content, source_type="url")
                if report.action == Action.BLOCK:
                    raise ValueError(f"보안 위협으로 인제스트 차단: {report.threats[0].truncated_detail()}")
                if report.action == Action.SANITIZE and report.sanitized_text is not None:
                    content = report.sanitized_text
                chunks_data = self._chunker.split_with_metadata(
                    content,
                    source_url=page["url"],
                    title=page.get("title", ""),
                )
                await self._save_chunks(document, chunks_data)
                total_chunks += len(chunks_data)

            await self._set_status(document, "completed", chunk_count=total_chunks)
        except Exception as exc:
            logger.exception("URL 인제스트 파이프라인 오류: doc_id=%d, %s", document.id, exc)
            await self._set_status(document, "failed", error=str(exc))
            raise

    async def ingest_file(self, document: Document) -> None:
        """업로드된 파일을 파싱하여 청킹 + 임베딩 후 저장합니다."""
        await self._set_status(document, "processing")
        # 갱신 시 기존 청크 삭제
        await self._db.execute(
            delete(Chunk).where(Chunk.document_id == document.id)
        )
        await self._db.flush()
        try:
            text = self._parser.parse(document.file_path, document.source_type)
            patterns = await boilerplate_svc.load_patterns(self._db, document.tenant_id)
            text = boilerplate_svc.apply(text, patterns)
            if not text:
                logger.warning(
                    "보일러플레이트 제거 후 본문이 비었습니다: doc_id=%d", document.id
                )
            report = content_inspector.inspect(text, source_type=document.source_type)
            if report.action == Action.BLOCK:
                raise ValueError(f"보안 위협으로 인제스트 차단: {report.threats[0].truncated_detail()}")
            if report.action == Action.SANITIZE and report.sanitized_text is not None:
                text = report.sanitized_text
            chunks_data = self._chunker.split_with_metadata(
                text,
                source_url=document.source_url,
                title=document.title,
            )
            await self._save_chunks(document, chunks_data)
            await self._set_status(document, "completed", chunk_count=len(chunks_data))
        except Exception as exc:
            logger.exception("파일 인제스트 파이프라인 오류: doc_id=%d, %s", document.id, exc)
            await self._set_status(document, "failed", error=str(exc))
            raise

    async def _save_chunks(self, document: Document, chunks_data: list[dict]) -> None:
        if not chunks_data:
            return

        # 중복 제거: 테넌트 내 이미 저장된 hash 조회
        hashes = [
            hashlib.sha256(c["content"].encode()).hexdigest() for c in chunks_data
        ]
        existing = await self._db.execute(
            select(Chunk.content_hash).where(
                Chunk.tenant_id == document.tenant_id,
                Chunk.content_hash.in_(hashes),
            )
        )
        existing_hashes = {row[0] for row in existing.fetchall()}

        new_chunks_data = [
            (data, h)
            for data, h in zip(chunks_data, hashes)
            if h not in existing_hashes
        ]

        skipped = len(chunks_data) - len(new_chunks_data)
        if skipped:
            logger.info("_save_chunks: %d 중복 청크 건너뜀 (tenant_id=%d)", skipped, document.tenant_id)

        if not new_chunks_data:
            return

        sanitized_chunks_data = []
        for data, h in new_chunks_data:
            clean_text, _ = chunk_sanitizer.sanitize(data["content"], data.get("index", 0))
            sanitized_chunks_data.append(({**data, "content": clean_text}, h))

        texts = [data["content"] for data, _ in sanitized_chunks_data]
        embeddings = await self._embedding_client.embed_batch(texts)

        chunks = [
            Chunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                content=data["content"],
                content_hash=h,
                embedding=embedding,
                chunk_index=data["index"],
                chunk_metadata={
                    k: v for k, v in data.items() if k not in ("content", "index")
                },
            )
            for (data, h), embedding in zip(sanitized_chunks_data, embeddings)
        ]
        self._db.add_all(chunks)
        await self._db.flush()

        await self._extract_graph(tenant_id=document.tenant_id, chunks=chunks)

    async def _extract_graph(self, tenant_id: int, chunks: list[Chunk]) -> None:
        if self._graph_extractor is None or self._graph_store is None:
            return

        import asyncio

        extractions = await asyncio.gather(
            *[self._graph_extractor.extract(chunk.content) for chunk in chunks],
            return_exceptions=True,
        )

        for chunk, extraction in zip(chunks, extractions):
            if isinstance(extraction, Exception):
                logger.warning("graph extraction failed for chunk %d: %s", chunk.id, extraction)
                continue
            if extraction.entities or getattr(extraction, "relationships", None):
                await self._graph_store.upsert(
                    tenant_id=tenant_id,
                    chunk_id=chunk.id,
                    extraction=extraction,
                )

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
        document.error_message = error[:1000] if error else None
        await self._db.commit()
