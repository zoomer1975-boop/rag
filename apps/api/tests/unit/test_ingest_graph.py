"""Phase 5 RED: IngestService에 GraphExtractor + GraphStore 통합.

`_save_chunks` 가 청크 저장 직후 각 청크에 대해
  extractor.extract(chunk.content) → store.upsert(tenant_id, chunk_id, extraction)
순으로 호출되는지를 단위 레벨에서 검증한다.

실제 DB 가 없어도 검증 가능하도록 `_extract_graph` 헬퍼 메서드의 행태만 테스트한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.models.chunk import Chunk
from app.services.graph_extractor import (
    ExtractedEntity,
    ExtractionResult,
)
from app.services.ingest import IngestService


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_service(extractor=None, store=None) -> IngestService:
    db = AsyncMock()
    embedding_client = AsyncMock()
    return IngestService(
        db=db,
        embedding_client=embedding_client,
        graph_extractor=extractor,
        graph_store=store,
    )


def _chunk(tenant_id: int, chunk_id: int, content: str) -> Chunk:
    c = Chunk(
        tenant_id=tenant_id,
        document_id=1,
        content=content,
        content_hash=f"h{chunk_id}",
        embedding=[0.0],
        chunk_index=chunk_id,
        chunk_metadata={},
    )
    c.id = chunk_id
    return c


class TestExtractGraphWiring:
    async def test_noop_when_extractor_missing(self) -> None:
        service = _make_service(extractor=None, store=AsyncMock())
        # store 가 있어도 extractor 가 없으면 아무 일도 하지 않아야 한다
        await service._extract_graph(tenant_id=1, chunks=[_chunk(1, 10, "hello")])
        # 예외가 터지지 않으면 통과 — 호출 대상이 없으므로 별도 assert 불필요

    async def test_noop_when_store_missing(self) -> None:
        extractor = AsyncMock()
        service = _make_service(extractor=extractor, store=None)
        await service._extract_graph(tenant_id=1, chunks=[_chunk(1, 10, "hello")])
        extractor.extract.assert_not_called()

    async def test_calls_extractor_and_store_per_chunk(self) -> None:
        entity = ExtractedEntity(name="Seoul", entity_type="location", description="")
        result = ExtractionResult(entities=(entity,))

        extractor = AsyncMock()
        extractor.extract = AsyncMock(return_value=result)
        store = AsyncMock()
        store.upsert = AsyncMock()

        service = _make_service(extractor=extractor, store=store)
        chunks = [_chunk(7, 100, "alpha"), _chunk(7, 101, "beta")]

        await service._extract_graph(tenant_id=7, chunks=chunks)

        assert extractor.extract.await_count == 2
        extractor.extract.assert_any_await("alpha")
        extractor.extract.assert_any_await("beta")

        assert store.upsert.await_count == 2
        call_kwargs = [c.kwargs for c in store.upsert.await_args_list]
        assert call_kwargs[0]["tenant_id"] == 7
        assert call_kwargs[0]["chunk_id"] == 100
        assert call_kwargs[0]["extraction"] is result
        assert call_kwargs[1]["chunk_id"] == 101

    async def test_skips_store_when_extraction_empty(self) -> None:
        extractor = AsyncMock()
        extractor.extract = AsyncMock(return_value=ExtractionResult())
        store = AsyncMock()

        service = _make_service(extractor=extractor, store=store)
        await service._extract_graph(tenant_id=1, chunks=[_chunk(1, 10, "hi")])

        extractor.extract.assert_awaited_once_with("hi")
        store.upsert.assert_not_called()

    async def test_extractor_exception_propagates(self) -> None:
        extractor = AsyncMock()
        extractor.extract = AsyncMock(side_effect=RuntimeError("boom"))
        store = AsyncMock()

        service = _make_service(extractor=extractor, store=store)

        with pytest.raises(RuntimeError, match="boom"):
            await service._extract_graph(tenant_id=1, chunks=[_chunk(1, 10, "x")])
        store.upsert.assert_not_called()
