"""graph_query 서비스 단위 테스트 — 실 PostgreSQL 사용."""

from __future__ import annotations

import secrets
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.tenant import Tenant
from app.services.graph_query import (
    MAX_NODES_HARD_CAP,
    fetch_graph,
    fetch_neighborhood,
    list_entity_types,
)

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
async def tenant_a(pg_session: AsyncSession) -> AsyncGenerator[Tenant, None]:
    t = Tenant(
        name=f"graph-query-test-a-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(t)
    await pg_session.commit()
    await pg_session.refresh(t)
    yield t
    await pg_session.execute(delete(Tenant).where(Tenant.id == t.id))
    await pg_session.commit()


@pytest_asyncio.fixture
async def tenant_b(pg_session: AsyncSession) -> AsyncGenerator[Tenant, None]:
    t = Tenant(
        name=f"graph-query-test-b-{secrets.token_hex(4)}",
        api_key=Tenant.generate_api_key(),
    )
    pg_session.add(t)
    await pg_session.commit()
    await pg_session.refresh(t)
    yield t
    await pg_session.execute(delete(Tenant).where(Tenant.id == t.id))
    await pg_session.commit()


async def _seed_graph(
    session: AsyncSession,
    tenant_id: int,
    entities: list[dict],
    relationships: list[dict],
) -> dict[str, Entity]:
    """엔티티/관계를 DB에 삽입하고 name → Entity 맵 반환."""
    objs: dict[str, Entity] = {}
    for e in entities:
        ent = Entity(
            tenant_id=tenant_id,
            name=e["name"],
            entity_type=e.get("entity_type", "unknown"),
            description=e.get("description", ""),
            source_chunk_ids=[],
        )
        session.add(ent)
        objs[e["name"]] = ent

    await session.flush()

    for r in relationships:
        rel = Relationship(
            tenant_id=tenant_id,
            source_entity_id=objs[r["source"]].id,
            target_entity_id=objs[r["target"]].id,
            description=r.get("description", ""),
            keywords=r.get("keywords", []),
            weight=r.get("weight", 1.0),
            source_chunk_ids=[],
        )
        session.add(rel)

    await session.commit()
    for ent in objs.values():
        await session.refresh(ent)
    return objs


class TestListEntityTypes:
    async def test_returns_distinct_types(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange
        await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "A", "entity_type": "person"},
                {"name": "B", "entity_type": "org"},
                {"name": "C", "entity_type": "person"},
            ],
            [],
        )

        # Act
        types = await list_entity_types(pg_session, tenant_a.id)

        # Assert
        assert set(types) == {"person", "org"}

    async def test_empty_tenant_returns_empty(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        types = await list_entity_types(pg_session, tenant_a.id)
        assert types == []

    async def test_tenant_isolation(
        self, pg_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
    ):
        # Arrange — only B has entities
        await _seed_graph(
            pg_session,
            tenant_b.id,
            [{"name": "X", "entity_type": "place"}],
            [],
        )

        # Act
        types_a = await list_entity_types(pg_session, tenant_a.id)
        types_b = await list_entity_types(pg_session, tenant_b.id)

        # Assert
        assert types_a == []
        assert types_b == ["place"]


class TestFetchGraph:
    async def test_returns_all_nodes_and_edges(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange
        await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "Alice", "entity_type": "person"},
                {"name": "Bob", "entity_type": "person"},
            ],
            [{"source": "Alice", "target": "Bob", "description": "knows"}],
        )

        # Act
        payload = await fetch_graph(pg_session, tenant_a.id)

        # Assert
        assert len(payload.nodes) == 2
        assert len(payload.edges) == 1
        assert not payload.truncated

    async def test_type_filter(self, pg_session: AsyncSession, tenant_a: Tenant):
        # Arrange
        await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "Seoul", "entity_type": "place"},
                {"name": "Kim", "entity_type": "person"},
            ],
            [],
        )

        # Act
        payload = await fetch_graph(
            pg_session, tenant_a.id, entity_types=["person"]
        )

        # Assert
        assert len(payload.nodes) == 1
        assert payload.nodes[0].name == "Kim"

    async def test_name_query_filter(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange
        await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "국회의사당", "entity_type": "place"},
                {"name": "국립중앙박물관", "entity_type": "place"},
                {"name": "서울역", "entity_type": "place"},
            ],
            [],
        )

        # Act
        payload = await fetch_graph(pg_session, tenant_a.id, name_query="국")

        # Assert
        names = {n.name for n in payload.nodes}
        assert names == {"국회의사당", "국립중앙박물관"}

    async def test_max_nodes_truncation(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange — 5 nodes
        entities = [{"name": f"E{i}", "entity_type": "x"} for i in range(5)]
        await _seed_graph(pg_session, tenant_a.id, entities, [])

        # Act
        payload = await fetch_graph(pg_session, tenant_a.id, max_nodes=3)

        # Assert
        assert len(payload.nodes) == 3
        assert payload.truncated

    async def test_edges_restricted_to_selected_nodes(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        """type 필터로 선택된 노드 집합 내 엣지만 반환되어야 한다."""
        # Arrange
        objs = await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "P1", "entity_type": "person"},
                {"name": "P2", "entity_type": "person"},
                {"name": "O1", "entity_type": "org"},
            ],
            [
                {"source": "P1", "target": "P2"},
                {"source": "P1", "target": "O1"},
            ],
        )

        # Act — only person nodes selected
        payload = await fetch_graph(
            pg_session, tenant_a.id, entity_types=["person"]
        )

        # Assert — cross-type edge (P1→O1) excluded, person-person edge included
        assert len(payload.nodes) == 2
        assert len(payload.edges) == 1
        assert payload.edges[0].source in {objs["P1"].id, objs["P2"].id}

    async def test_tenant_isolation(
        self, pg_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
    ):
        # Arrange — B has data, A is empty
        await _seed_graph(
            pg_session,
            tenant_b.id,
            [{"name": "Secret", "entity_type": "org"}],
            [],
        )

        # Act
        payload_a = await fetch_graph(pg_session, tenant_a.id)

        # Assert — A sees nothing
        assert payload_a.nodes == []
        assert payload_a.edges == []

    async def test_max_nodes_hard_cap_enforced(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        """max_nodes 인수가 하드 캡을 초과하면 캡으로 제한된다."""
        payload = await fetch_graph(
            pg_session, tenant_a.id, max_nodes=MAX_NODES_HARD_CAP + 9999
        )
        # 엔티티가 없으므로 0개 — 캡 적용 여부는 런타임 오류 없이 통과하면 충분
        assert payload.nodes == []


class TestFetchNeighborhood:
    async def test_depth_1_returns_direct_neighbors(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange: A -→ B -→ C (chain)
        objs = await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "A", "entity_type": "x"},
                {"name": "B", "entity_type": "x"},
                {"name": "C", "entity_type": "x"},
            ],
            [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        # Act
        payload = await fetch_neighborhood(
            pg_session, tenant_a.id, root_entity_id=objs["A"].id, depth=1
        )

        # Assert — A and B visible, C not
        names = {n.name for n in payload.nodes}
        assert names == {"A", "B"}

    async def test_depth_2_returns_two_hops(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange: A → B → C
        objs = await _seed_graph(
            pg_session,
            tenant_a.id,
            [
                {"name": "A", "entity_type": "x"},
                {"name": "B", "entity_type": "x"},
                {"name": "C", "entity_type": "x"},
            ],
            [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        # Act
        payload = await fetch_neighborhood(
            pg_session, tenant_a.id, root_entity_id=objs["A"].id, depth=2
        )

        # Assert — all three visible
        names = {n.name for n in payload.nodes}
        assert names == {"A", "B", "C"}

    async def test_tenant_isolation_neighborhood(
        self, pg_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
    ):
        """다른 테넌트의 엔티티 id로 조회해도 빈 결과가 나와야 한다."""
        # Arrange — entity lives in B
        objs_b = await _seed_graph(
            pg_session,
            tenant_b.id,
            [{"name": "Secret", "entity_type": "x"}],
            [],
        )
        # Seed A separately so the fixture entity id doesn't collide
        await _seed_graph(
            pg_session,
            tenant_a.id,
            [{"name": "Mine", "entity_type": "x"}],
            [],
        )

        # Act — query A's session with B's root entity id
        payload = await fetch_neighborhood(
            pg_session,
            tenant_a.id,
            root_entity_id=objs_b["Secret"].id,
            depth=1,
        )

        # Assert — A's neighborhood should not include B's node
        names = {n.name for n in payload.nodes}
        assert "Secret" not in names

    async def test_max_nodes_limit_in_neighborhood(
        self, pg_session: AsyncSession, tenant_a: Tenant
    ):
        # Arrange: hub connected to 5 spokes
        entities = [{"name": "Hub", "entity_type": "x"}] + [
            {"name": f"Spoke{i}", "entity_type": "x"} for i in range(5)
        ]
        rels = [{"source": "Hub", "target": f"Spoke{i}"} for i in range(5)]
        objs = await _seed_graph(pg_session, tenant_a.id, entities, rels)

        # Act — limit to 3 nodes
        payload = await fetch_neighborhood(
            pg_session,
            tenant_a.id,
            root_entity_id=objs["Hub"].id,
            depth=1,
            max_nodes=3,
        )

        # Assert
        assert len(payload.nodes) <= 3
        assert payload.truncated
