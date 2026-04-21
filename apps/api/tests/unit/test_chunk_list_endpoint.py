"""청크 목록 조회 엔드포인트 단위 테스트"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.tenant import Tenant


def _make_tenant(tid: int = 1) -> Tenant:
    t = MagicMock(spec=Tenant)
    t.id = tid
    return t


def _make_document(doc_id: int = 10, tenant_id: int = 1) -> Document:
    d = MagicMock(spec=Document)
    d.id = doc_id
    d.tenant_id = tenant_id
    return d


def _make_chunk(chunk_id: int, chunk_index: int, content: str, tenant_id: int = 1, doc_id: int = 10) -> Chunk:
    c = MagicMock(spec=Chunk)
    c.id = chunk_id
    c.chunk_index = chunk_index
    c.content = content
    c.tenant_id = tenant_id
    c.document_id = doc_id
    c.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return c


class TestListDocumentChunks:
    """list_document_chunks 엔드포인트 로직 테스트"""

    @pytest.mark.asyncio
    async def test_returns_404_when_doc_not_found(self):
        """문서가 없으면 404를 반환한다."""
        from fastapi import HTTPException

        from app.routers.ingest import list_document_chunks

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        tenant = _make_tenant(tid=1)

        with pytest.raises(HTTPException) as exc_info:
            await list_document_chunks(doc_id=999, tenant=tenant, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_doc_belongs_to_other_tenant(self):
        """다른 테넌트의 문서를 조회하면 404를 반환한다 (테넌트 격리)."""
        from fastapi import HTTPException

        from app.routers.ingest import list_document_chunks

        db = AsyncMock()
        doc = _make_document(doc_id=10, tenant_id=2)  # 다른 테넌트 소유
        db.get = AsyncMock(return_value=doc)
        tenant = _make_tenant(tid=1)  # 현재 테넌트

        with pytest.raises(HTTPException) as exc_info:
            await list_document_chunks(doc_id=10, tenant=tenant, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_chunks_in_order(self):
        """청크를 chunk_index 순으로 반환한다."""
        from app.routers.ingest import list_document_chunks

        chunks = [
            _make_chunk(1, 0, "첫 번째 청크"),
            _make_chunk(2, 1, "두 번째 청크"),
            _make_chunk(3, 2, "세 번째 청크"),
        ]

        db = AsyncMock()
        doc = _make_document(doc_id=10, tenant_id=1)
        db.get = AsyncMock(return_value=doc)

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=3)

        items_result = MagicMock()
        items_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=chunks)))

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        tenant = _make_tenant(tid=1)
        result = await list_document_chunks(doc_id=10, tenant=tenant, db=db, limit=50, offset=0)

        assert result.total == 3
        assert len(result.items) == 3
        assert result.items[0].chunk_index == 0
        assert result.items[1].chunk_index == 1

    @pytest.mark.asyncio
    async def test_empty_document_returns_zero_total(self):
        """청크가 없는 문서는 total=0, items=[] 을 반환한다."""
        from app.routers.ingest import list_document_chunks

        db = AsyncMock()
        doc = _make_document(doc_id=10, tenant_id=1)
        db.get = AsyncMock(return_value=doc)

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=0)

        items_result = MagicMock()
        items_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        tenant = _make_tenant(tid=1)
        result = await list_document_chunks(doc_id=10, tenant=tenant, db=db, limit=50, offset=0)

        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_pagination_params_passed_through(self):
        """limit/offset 파라미터가 응답에 반영된다."""
        from app.routers.ingest import list_document_chunks

        db = AsyncMock()
        doc = _make_document(doc_id=10, tenant_id=1)
        db.get = AsyncMock(return_value=doc)

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=100)

        items_result = MagicMock()
        items_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        tenant = _make_tenant(tid=1)
        result = await list_document_chunks(doc_id=10, tenant=tenant, db=db, limit=20, offset=40)

        assert result.limit == 20
        assert result.offset == 40
        assert result.total == 100
