"""Graph RAG 쿼리 서비스 — 테넌트별 엔티티/관계 그래프 조회."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.relationship import Relationship

MAX_NODES_HARD_CAP = 2000


@dataclass(frozen=True)
class GraphNode:
    id: int
    name: str
    entity_type: str
    description: str
    degree: int
    chunk_count: int


@dataclass(frozen=True)
class GraphEdge:
    id: int
    source: int
    target: int
    description: str
    keywords: list[str]
    weight: float


@dataclass(frozen=True)
class GraphPayload:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


async def list_entity_types(db: AsyncSession, tenant_id: int) -> list[str]:
    """테넌트의 고유 엔티티 타입 목록."""
    result = await db.execute(
        select(Entity.entity_type)
        .where(Entity.tenant_id == tenant_id)
        .distinct()
        .order_by(Entity.entity_type)
    )
    return list(result.scalars().all())


async def fetch_graph(
    db: AsyncSession,
    tenant_id: int,
    *,
    entity_types: list[str] | None = None,
    name_query: str | None = None,
    max_nodes: int = 500,
) -> GraphPayload:
    """테넌트 전체 그래프 (필터 옵션 포함)."""
    max_nodes = min(max_nodes, MAX_NODES_HARD_CAP)

    # degree 서브쿼리
    degree_sq = (
        select(
            Relationship.source_entity_id.label("entity_id"),
            func.count(Relationship.id).label("cnt"),
        )
        .where(Relationship.tenant_id == tenant_id)
        .group_by(Relationship.source_entity_id)
        .union_all(
            select(
                Relationship.target_entity_id.label("entity_id"),
                func.count(Relationship.id).label("cnt"),
            )
            .where(Relationship.tenant_id == tenant_id)
            .group_by(Relationship.target_entity_id)
        )
        .subquery()
    )

    degree_agg_sq = (
        select(
            degree_sq.c.entity_id,
            func.sum(degree_sq.c.cnt).label("degree"),
        )
        .group_by(degree_sq.c.entity_id)
        .subquery()
    )

    q = (
        select(Entity, func.coalesce(degree_agg_sq.c.degree, 0).label("degree"))
        .outerjoin(degree_agg_sq, Entity.id == degree_agg_sq.c.entity_id)
        .where(Entity.tenant_id == tenant_id)
    )

    if entity_types:
        q = q.where(Entity.entity_type.in_(entity_types))

    if name_query and name_query.strip():
        q = q.where(Entity.name.ilike(f"%{name_query.strip()}%"))

    q = q.order_by(degree_agg_sq.c.degree.desc().nullslast()).limit(max_nodes + 1)

    result = await db.execute(q)
    rows = result.all()

    truncated = len(rows) > max_nodes
    rows = rows[:max_nodes]

    node_ids = {row.Entity.id for row in rows}
    nodes = [
        GraphNode(
            id=row.Entity.id,
            name=row.Entity.name,
            entity_type=row.Entity.entity_type,
            description=row.Entity.description,
            degree=int(row.degree),
            chunk_count=len(row.Entity.source_chunk_ids or []),
        )
        for row in rows
    ]

    edges = await _fetch_edges_for_nodes(db, tenant_id, node_ids)
    return GraphPayload(nodes=nodes, edges=edges, truncated=truncated)


async def fetch_neighborhood(
    db: AsyncSession,
    tenant_id: int,
    *,
    root_entity_id: int,
    depth: int = 1,
    max_nodes: int = 200,
) -> GraphPayload:
    """특정 엔티티 중심 N-hop 서브그래프 (depth 최대 2)."""
    depth = min(depth, 2)
    max_nodes = min(max_nodes, MAX_NODES_HARD_CAP)

    collected_ids: set[int] = {root_entity_id}
    frontier: set[int] = {root_entity_id}

    for _ in range(depth):
        if not frontier or len(collected_ids) >= max_nodes:
            break

        rel_result = await db.execute(
            select(Relationship.source_entity_id, Relationship.target_entity_id)
            .where(
                Relationship.tenant_id == tenant_id,
                or_(
                    Relationship.source_entity_id.in_(frontier),
                    Relationship.target_entity_id.in_(frontier),
                ),
            )
        )
        neighbors: set[int] = set()
        for src, tgt in rel_result.all():
            neighbors.add(src)
            neighbors.add(tgt)

        new_ids = neighbors - collected_ids
        collected_ids.update(new_ids)
        frontier = new_ids

        if len(collected_ids) >= max_nodes:
            collected_ids = set(list(collected_ids)[:max_nodes])
            break

    truncated = len(collected_ids) >= max_nodes

    entity_result = await db.execute(
        select(Entity).where(
            Entity.tenant_id == tenant_id,
            Entity.id.in_(collected_ids),
        )
    )
    entities = entity_result.scalars().all()

    node_ids = {e.id for e in entities}
    edges = await _fetch_edges_for_nodes(db, tenant_id, node_ids)

    degree_map: dict[int, int] = {}
    for edge in edges:
        degree_map[edge.source] = degree_map.get(edge.source, 0) + 1
        degree_map[edge.target] = degree_map.get(edge.target, 0) + 1

    nodes = [
        GraphNode(
            id=e.id,
            name=e.name,
            entity_type=e.entity_type,
            description=e.description,
            degree=degree_map.get(e.id, 0),
            chunk_count=len(e.source_chunk_ids or []),
        )
        for e in entities
    ]

    return GraphPayload(nodes=nodes, edges=edges, truncated=truncated)


async def _fetch_edges_for_nodes(
    db: AsyncSession, tenant_id: int, node_ids: set[int]
) -> list[GraphEdge]:
    """주어진 노드 집합 안에서만 존재하는 엣지 조회."""
    if not node_ids:
        return []

    result = await db.execute(
        select(Relationship).where(
            Relationship.tenant_id == tenant_id,
            Relationship.source_entity_id.in_(node_ids),
            Relationship.target_entity_id.in_(node_ids),
        )
    )
    rels = result.scalars().all()

    return [
        GraphEdge(
            id=r.id,
            source=r.source_entity_id,
            target=r.target_entity_id,
            description=r.description,
            keywords=list(r.keywords or []),
            weight=r.weight,
        )
        for r in rels
    ]
