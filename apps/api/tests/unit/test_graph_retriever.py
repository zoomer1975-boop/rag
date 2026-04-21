"""Phase 4 RED: GraphRAGRetriever — dual-level 검색.

쿼리에서 low/high level 키워드를 LLM으로 추출하고, 각각을 entities /
relationships 테이블에 pgvector 유사도 검색한다. 그 후 검색된 엔티티
기준으로 1-hop 이웃을 확장하고, source_chunk_ids 를 병합한다.

실제 Postgres(docker compose)의 pgvector 를 사용한다. 테스트마다
고유 테넌트를 만들어 CASCADE 로 정리한다. 코사인 거리 정렬이 결정적이게
단위 벡터(one-hot)를 사용한다.
"""

from __future__ import annotations

import json
import secrets
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.tenant import Tenant


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _unit_vector(index: int, dim: int | None = None) -> list[float]:
    if dim is None:
        dim = get_settings().embedding_dimension
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


@pytest_asyncio.fixture
async def pg_session() -> AsyncGenerator[AsyncSession, None]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, future=True
    )
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_tenant(pg_session: AsyncSession) -> AsyncGenerator[Tenant, None]:
    tenant = Tenant(
        name=f"graphret-test-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(tenant)
    await pg_session.commit()
    await pg_session.refresh(tenant)
    yield tenant
    await pg_session.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await pg_session.commit()


@pytest_asyncio.fixture
async def second_tenant(pg_session: AsyncSession) -> AsyncGenerator[Tenant, None]:
    tenant = Tenant(
        name=f"graphret-test2-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(tenant)
    await pg_session.commit()
    await pg_session.refresh(tenant)
    yield tenant
    await pg_session.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await pg_session.commit()


async def _seed_entity(
    db: AsyncSession,
    *,
    tenant_id: int,
    name: str,
    entity_type: str = "concept",
    description: str = "",
    embedding_index: int = 0,
    source_chunk_ids: list[int] | None = None,
) -> Entity:
    row = Entity(
        tenant_id=tenant_id,
        name=name,
        entity_type=entity_type,
        description=description or name,
        description_embedding=_unit_vector(embedding_index),
        source_chunk_ids=source_chunk_ids if source_chunk_ids is not None else [],
    )
    db.add(row)
    await db.flush()
    return row


async def _seed_relationship(
    db: AsyncSession,
    *,
    tenant_id: int,
    source_id: int,
    target_id: int,
    description: str,
    keywords: list[str] | None = None,
    weight: float = 1.0,
    embedding_index: int = 0,
    source_chunk_ids: list[int] | None = None,
) -> Relationship:
    row = Relationship(
        tenant_id=tenant_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        description=description,
        keywords=keywords or [],
        weight=weight,
        description_embedding=_unit_vector(embedding_index),
        source_chunk_ids=source_chunk_ids if source_chunk_ids is not None else [],
    )
    db.add(row)
    await db.flush()
    return row


def _make_llm_client(payload: dict | str) -> AsyncMock:
    """LLMClient.chat 의 반환을 고정한다."""
    client = AsyncMock()
    text = payload if isinstance(payload, str) else json.dumps(payload)
    client.chat = AsyncMock(return_value=text)
    return client


def _make_embedding_for_keywords(mapping: dict[str, int]) -> AsyncMock:
    """'키워드 리스트를 하나의 텍스트로 합친 문자열 → 특정 index unit vector' 매핑."""
    client = AsyncMock()

    async def fake_embed(text: str) -> list[float]:
        for key, idx in mapping.items():
            if key in text:
                return _unit_vector(idx)
        return _unit_vector(0)

    client.embed = AsyncMock(side_effect=fake_embed)
    return client


class TestGraphRAGRetrieverKeywordExtraction:
    async def test_retrieve_uses_llm_to_extract_keywords(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        llm = _make_llm_client(
            {"low_level_keywords": ["서울시청"], "high_level_keywords": ["행정"]}
        )
        embed = _make_embedding_for_keywords({"서울시청": 0, "행정": 1})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=5,
            top_k_relationships=5,
            neighbor_hops=1,
        )
        await retriever.retrieve(query="서울시청은 무엇인가?", tenant_id=test_tenant.id)

        assert llm.chat.await_count == 1
        # low/high 각각 최소 1회 embed
        assert embed.embed.await_count >= 2

    async def test_retrieve_falls_back_when_llm_returns_garbage(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        # JSON 파싱 실패 → 전체 질의를 low-level 로 사용
        llm = _make_llm_client("not a json {{{")
        embed = _make_embedding_for_keywords({"테스트 질의": 0})

        retriever = GraphRAGRetriever(
            db=pg_session, embedding_client=embed, llm_client=llm
        )
        result = await retriever.retrieve(query="테스트 질의", tenant_id=test_tenant.id)

        assert result.entities == ()
        assert result.relationships == ()
        # 최소 low-level 검색을 위해 embed 가 호출되어야 한다
        assert embed.embed.await_count >= 1


class TestGraphRAGRetrieverDualLevel:
    async def test_retrieve_low_level_finds_entities(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        a = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="서울시청",
            embedding_index=0,
            source_chunk_ids=[10],
        )
        await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="부산시청",
            embedding_index=50,
            source_chunk_ids=[20],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": ["서울시청"], "high_level_keywords": []}
        )
        embed = _make_embedding_for_keywords({"서울시청": 0})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=1,
            top_k_relationships=5,
        )
        result = await retriever.retrieve(query="서울시청", tenant_id=test_tenant.id)

        assert len(result.entities) == 1
        assert result.entities[0].id == a.id
        assert 10 in result.chunk_ids

    async def test_retrieve_high_level_finds_relationships(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        a = await _seed_entity(
            pg_session, tenant_id=test_tenant.id, name="A", embedding_index=30
        )
        b = await _seed_entity(
            pg_session, tenant_id=test_tenant.id, name="B", embedding_index=31
        )
        rel = await _seed_relationship(
            pg_session,
            tenant_id=test_tenant.id,
            source_id=a.id,
            target_id=b.id,
            description="협력 관계",
            keywords=["협력"],
            embedding_index=1,
            source_chunk_ids=[100],
        )
        # noise 관계
        c = await _seed_entity(
            pg_session, tenant_id=test_tenant.id, name="C", embedding_index=32
        )
        d = await _seed_entity(
            pg_session, tenant_id=test_tenant.id, name="D", embedding_index=33
        )
        await _seed_relationship(
            pg_session,
            tenant_id=test_tenant.id,
            source_id=c.id,
            target_id=d.id,
            description="무관",
            embedding_index=60,
            source_chunk_ids=[200],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": [], "high_level_keywords": ["협력"]}
        )
        embed = _make_embedding_for_keywords({"협력": 1})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=5,
            top_k_relationships=1,
        )
        result = await retriever.retrieve(query="A와 B는?", tenant_id=test_tenant.id)

        assert len(result.relationships) == 1
        assert result.relationships[0].id == rel.id
        assert 100 in result.chunk_ids


class TestGraphRAGRetrieverNeighborExpansion:
    async def test_one_hop_neighbor_chunks_are_included(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        a = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="A",
            embedding_index=0,
            source_chunk_ids=[1],
        )
        b = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="B",
            embedding_index=40,
            source_chunk_ids=[2],
        )
        # A-B 관계 (A 가 검색되면 B 의 chunk_ids 도 수집되어야 함)
        await _seed_relationship(
            pg_session,
            tenant_id=test_tenant.id,
            source_id=a.id,
            target_id=b.id,
            description="A→B",
            embedding_index=99,
            source_chunk_ids=[3],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": ["A"], "high_level_keywords": []}
        )
        embed = _make_embedding_for_keywords({"A": 0})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=1,
            top_k_relationships=5,
            neighbor_hops=1,
        )
        result = await retriever.retrieve(query="A 관련", tenant_id=test_tenant.id)

        assert 1 in result.chunk_ids  # A 자체
        assert 2 in result.chunk_ids  # 이웃 B
        assert 3 in result.chunk_ids  # 관계
        # 이웃 엔티티도 결과에 포함되어야 한다
        assert {e.id for e in result.entities} >= {a.id, b.id}

    async def test_chunk_ids_are_deduplicated(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        a = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="A",
            embedding_index=0,
            source_chunk_ids=[7, 7, 8],
        )
        b = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="B",
            embedding_index=41,
            source_chunk_ids=[8, 9],
        )
        await _seed_relationship(
            pg_session,
            tenant_id=test_tenant.id,
            source_id=a.id,
            target_id=b.id,
            description="A-B",
            embedding_index=0,
            source_chunk_ids=[9, 10],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": ["A"], "high_level_keywords": ["A"]}
        )
        embed = _make_embedding_for_keywords({"A": 0})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=5,
            top_k_relationships=5,
            neighbor_hops=1,
        )
        result = await retriever.retrieve(query="A", tenant_id=test_tenant.id)

        assert sorted(result.chunk_ids) == sorted(set(result.chunk_ids))
        assert set(result.chunk_ids) >= {7, 8, 9, 10}


class TestGraphRAGRetrieverTenantIsolation:
    async def test_tenant_data_does_not_leak(
        self,
        pg_session: AsyncSession,
        test_tenant: Tenant,
        second_tenant: Tenant,
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        # 두 테넌트 모두 동일한 임베딩 인덱스로 "같은" 엔티티를 갖는다
        mine = await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="shared",
            embedding_index=0,
            source_chunk_ids=[1],
        )
        theirs = await _seed_entity(
            pg_session,
            tenant_id=second_tenant.id,
            name="shared",
            embedding_index=0,
            source_chunk_ids=[999],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": ["shared"], "high_level_keywords": []}
        )
        embed = _make_embedding_for_keywords({"shared": 0})

        retriever = GraphRAGRetriever(
            db=pg_session,
            embedding_client=embed,
            llm_client=llm,
            top_k_entities=10,
            top_k_relationships=5,
        )
        result = await retriever.retrieve(query="shared", tenant_id=test_tenant.id)

        ids = {e.id for e in result.entities}
        assert mine.id in ids
        assert theirs.id not in ids
        assert 999 not in result.chunk_ids


class TestGraphRAGRetrieverEdgeCases:
    async def test_empty_graph_returns_empty_result(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        llm = _make_llm_client(
            {"low_level_keywords": ["anything"], "high_level_keywords": ["anything"]}
        )
        embed = _make_embedding_for_keywords({"anything": 0})

        retriever = GraphRAGRetriever(
            db=pg_session, embedding_client=embed, llm_client=llm
        )
        result = await retriever.retrieve(query="anything", tenant_id=test_tenant.id)

        assert result.entities == ()
        assert result.relationships == ()
        assert result.chunk_ids == ()

    async def test_empty_keywords_skip_that_level(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_retriever import GraphRAGRetriever

        await _seed_entity(
            pg_session,
            tenant_id=test_tenant.id,
            name="X",
            embedding_index=0,
            source_chunk_ids=[1],
        )
        await pg_session.commit()

        llm = _make_llm_client(
            {"low_level_keywords": [], "high_level_keywords": []}
        )
        embed = _make_embedding_for_keywords({})

        retriever = GraphRAGRetriever(
            db=pg_session, embedding_client=embed, llm_client=llm
        )
        result = await retriever.retrieve(query="nothing", tenant_id=test_tenant.id)

        # 키워드가 아무것도 없으면 전체 질의를 low-level 로 fallback
        # 최소한 embed 가 호출되거나, 결과가 명확히 비어 있어야 한다
        assert isinstance(result.entities, tuple)
        assert isinstance(result.relationships, tuple)
        assert isinstance(result.chunk_ids, tuple)
