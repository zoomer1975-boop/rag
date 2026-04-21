"""Phase 3 RED: GraphStore — 추출된 엔티티/관계를 Postgres에 UPSERT + 병합.

SQLite는 pgvector Vector와 PostgreSQL ARRAY를 지원하지 않으므로
실제 Postgres(docker compose의 DB)를 사용한다. 테스트마다 고유한
테넌트를 만들어 CASCADE로 자동 정리한다.
"""

from __future__ import annotations

import secrets
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.tenant import Tenant


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


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
        name=f"graphstore-test-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(tenant)
    await pg_session.commit()
    await pg_session.refresh(tenant)
    yield tenant
    # CASCADE 로 entities/relationships 도 함께 삭제된다
    await pg_session.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await pg_session.commit()


@pytest_asyncio.fixture
async def second_tenant(pg_session: AsyncSession) -> AsyncGenerator[Tenant, None]:
    tenant = Tenant(
        name=f"graphstore-test2-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(tenant)
    await pg_session.commit()
    await pg_session.refresh(tenant)
    yield tenant
    await pg_session.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await pg_session.commit()


def _make_embedding_client(dim: int | None = None) -> AsyncMock:
    """description별로 고정 벡터를 돌려주는 모킹 임베딩 클라이언트."""
    if dim is None:
        dim = get_settings().embedding_dimension
    client = AsyncMock()

    async def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        return [[float((hash(t) % 100) / 100.0)] * dim for t in texts]

    client.embed_batch = AsyncMock(side_effect=fake_embed_batch)
    return client


def _make_extraction(entities: list[dict], relationships: list[dict]):
    from app.services.graph_extractor import (
        ExtractedEntity,
        ExtractedRelationship,
        ExtractionResult,
    )

    ent_objs = tuple(ExtractedEntity(**e) for e in entities)
    rel_objs = tuple(ExtractedRelationship(**r) for r in relationships)
    return ExtractionResult(entities=ent_objs, relationships=rel_objs)


class TestGraphStoreUpsertEntities:
    async def test_upsert_entities_creates_new(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        extraction = _make_extraction(
            entities=[
                {"name": "서울시청", "entity_type": "organization", "description": "행정 본청"},
                {"name": "박원순", "entity_type": "person", "description": "전 시장"},
            ],
            relationships=[],
        )

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        await store.upsert(tenant_id=test_tenant.id, chunk_id=1, extraction=extraction)

        rows = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id).order_by(Entity.name)
            )
        ).scalars().all()
        assert {e.name for e in rows} == {"박원순", "서울시청"}
        for row in rows:
            assert row.source_chunk_ids == [1]
            assert row.description_embedding is not None

    async def test_upsert_entities_merges_by_name_type(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())

        first = _make_extraction(
            entities=[{"name": "서울시청", "entity_type": "organization", "description": "행정 본청"}],
            relationships=[],
        )
        await store.upsert(tenant_id=test_tenant.id, chunk_id=1, extraction=first)

        second = _make_extraction(
            entities=[{"name": "서울시청", "entity_type": "organization", "description": "수도의 청사"}],
            relationships=[],
        )
        await store.upsert(tenant_id=test_tenant.id, chunk_id=2, extraction=second)

        rows = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        merged = rows[0]
        assert sorted(merged.source_chunk_ids) == [1, 2]
        # 두 설명이 어떤 방식으로든 보존되어야 한다
        assert "행정 본청" in merged.description or "수도의 청사" in merged.description

    async def test_upsert_entity_name_is_case_insensitive_for_merge(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())

        await store.upsert(
            tenant_id=test_tenant.id,
            chunk_id=1,
            extraction=_make_extraction(
                entities=[{"name": "Seoul", "entity_type": "location", "description": "a"}],
                relationships=[],
            ),
        )
        await store.upsert(
            tenant_id=test_tenant.id,
            chunk_id=2,
            extraction=_make_extraction(
                entities=[{"name": "seoul", "entity_type": "location", "description": "b"}],
                relationships=[],
            ),
        )

        rows = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert sorted(rows[0].source_chunk_ids) == [1, 2]

    async def test_source_chunk_ids_accumulate_without_duplicates(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        payload = _make_extraction(
            entities=[{"name": "A", "entity_type": "concept", "description": "d"}],
            relationships=[],
        )

        await store.upsert(tenant_id=test_tenant.id, chunk_id=42, extraction=payload)
        await store.upsert(tenant_id=test_tenant.id, chunk_id=42, extraction=payload)

        rows = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].source_chunk_ids == [42]


class TestGraphStoreUpsertRelationships:
    async def test_upsert_relationships_resolves_by_name(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        extraction = _make_extraction(
            entities=[
                {"name": "A", "entity_type": "concept", "description": "a"},
                {"name": "B", "entity_type": "concept", "description": "b"},
            ],
            relationships=[
                {
                    "source": "A",
                    "target": "B",
                    "description": "A→B",
                    "keywords": ("k1", "k2"),
                    "weight": 0.7,
                }
            ],
        )

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        await store.upsert(tenant_id=test_tenant.id, chunk_id=10, extraction=extraction)

        entities = {
            e.name: e
            for e in (
                await pg_session.execute(
                    select(Entity).where(Entity.tenant_id == test_tenant.id)
                )
            ).scalars().all()
        }

        rels = (
            await pg_session.execute(
                select(Relationship).where(Relationship.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert len(rels) == 1
        rel = rels[0]
        assert rel.source_entity_id == entities["A"].id
        assert rel.target_entity_id == entities["B"].id
        assert rel.description == "A→B"
        assert list(rel.keywords) == ["k1", "k2"]
        assert abs(rel.weight - 0.7) < 1e-6
        assert rel.source_chunk_ids == [10]
        assert rel.description_embedding is not None

    async def test_upsert_skips_relationship_when_entity_missing(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        """GraphExtractor가 걸러주긴 하지만, 방어적으로 이중 검증한다."""
        from app.services.graph_extractor import (
            ExtractedEntity,
            ExtractedRelationship,
            ExtractionResult,
        )
        from app.services.graph_store import GraphStore

        extraction = ExtractionResult(
            entities=(ExtractedEntity(name="A", entity_type="concept", description="a"),),
            # Extractor가 걸러내지 못한 dangling edge를 직접 주입
            relationships=(
                ExtractedRelationship(source="A", target="GHOST", description="dangling"),
            ),
        )

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        await store.upsert(tenant_id=test_tenant.id, chunk_id=1, extraction=extraction)

        rels = (
            await pg_session.execute(
                select(Relationship).where(Relationship.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert rels == []

    async def test_relationship_source_chunk_ids_accumulate(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_store import GraphStore

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        payload = _make_extraction(
            entities=[
                {"name": "A", "entity_type": "concept", "description": "a"},
                {"name": "B", "entity_type": "concept", "description": "b"},
            ],
            relationships=[
                {
                    "source": "A",
                    "target": "B",
                    "description": "same rel",
                    "keywords": ("k",),
                    "weight": 0.5,
                }
            ],
        )

        await store.upsert(tenant_id=test_tenant.id, chunk_id=11, extraction=payload)
        await store.upsert(tenant_id=test_tenant.id, chunk_id=12, extraction=payload)

        rels = (
            await pg_session.execute(
                select(Relationship).where(Relationship.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert len(rels) == 1
        assert sorted(rels[0].source_chunk_ids) == [11, 12]


class TestGraphStoreTenantIsolation:
    async def test_tenant_isolation(
        self,
        pg_session: AsyncSession,
        test_tenant: Tenant,
        second_tenant: Tenant,
    ):
        from app.services.graph_store import GraphStore

        store = GraphStore(db=pg_session, embedding_client=_make_embedding_client())
        payload = _make_extraction(
            entities=[{"name": "shared", "entity_type": "concept", "description": "x"}],
            relationships=[],
        )

        await store.upsert(tenant_id=test_tenant.id, chunk_id=1, extraction=payload)
        await store.upsert(tenant_id=second_tenant.id, chunk_id=2, extraction=payload)

        t1 = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        t2 = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == second_tenant.id)
            )
        ).scalars().all()

        assert len(t1) == 1 and t1[0].source_chunk_ids == [1]
        assert len(t2) == 1 and t2[0].source_chunk_ids == [2]
        assert t1[0].id != t2[0].id


class TestGraphStoreEdgeCases:
    async def test_empty_extraction_is_no_op(
        self, pg_session: AsyncSession, test_tenant: Tenant
    ):
        from app.services.graph_extractor import ExtractionResult
        from app.services.graph_store import GraphStore

        embed = _make_embedding_client()
        store = GraphStore(db=pg_session, embedding_client=embed)
        await store.upsert(
            tenant_id=test_tenant.id,
            chunk_id=1,
            extraction=ExtractionResult(),
        )

        rows = (
            await pg_session.execute(
                select(Entity).where(Entity.tenant_id == test_tenant.id)
            )
        ).scalars().all()
        assert rows == []
        embed.embed_batch.assert_not_called()
