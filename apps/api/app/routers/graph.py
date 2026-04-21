"""Graph RAG 그래프 API — 테넌트별 엔티티/관계 탐색."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.tenant import Tenant
from app.services.graph_query import (
    fetch_graph,
    fetch_neighborhood,
    list_entity_types,
)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.get("/summary")
async def get_graph_summary(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """테넌트 그래프 요약 — 엔티티/관계 수, 타입별 분포."""
    entity_count = await db.scalar(
        select(func.count(Entity.id)).where(Entity.tenant_id == tenant.id)
    )
    rel_count = await db.scalar(
        select(func.count(Relationship.id)).where(Relationship.tenant_id == tenant.id)
    )

    type_result = await db.execute(
        select(Entity.entity_type, func.count(Entity.id).label("count"))
        .where(Entity.tenant_id == tenant.id)
        .group_by(Entity.entity_type)
        .order_by(func.count(Entity.id).desc())
    )
    entity_types = [
        {"type": row.entity_type, "count": row.count} for row in type_result.all()
    ]

    return {
        "entity_count": entity_count or 0,
        "relationship_count": rel_count or 0,
        "entity_types": entity_types,
    }


@router.get("/")
async def get_graph(
    types: list[str] = Query(default=[]),
    q: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """전체 그래프 데이터 (필터: 엔티티 타입, 이름 검색, 노드 수 제한)."""
    payload = await fetch_graph(
        db,
        tenant.id,
        entity_types=types or None,
        name_query=q,
        max_nodes=limit,
    )
    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "entity_type": n.entity_type,
                "description": n.description,
                "degree": n.degree,
                "chunk_count": n.chunk_count,
            }
            for n in payload.nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "description": e.description,
                "keywords": e.keywords,
                "weight": e.weight,
            }
            for e in payload.edges
        ],
        "truncated": payload.truncated,
    }


@router.get("/neighborhood/{entity_id}")
async def get_neighborhood(
    entity_id: int,
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=200, ge=1, le=2000),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """특정 엔티티 중심 N-hop 서브그래프."""
    entity = await db.scalar(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.tenant_id == tenant.id,
        )
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    payload = await fetch_neighborhood(
        db,
        tenant.id,
        root_entity_id=entity_id,
        depth=depth,
        max_nodes=limit,
    )
    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "entity_type": n.entity_type,
                "description": n.description,
                "degree": n.degree,
                "chunk_count": n.chunk_count,
            }
            for n in payload.nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "description": e.description,
                "keywords": e.keywords,
                "weight": e.weight,
            }
            for e in payload.edges
        ],
        "truncated": payload.truncated,
    }
