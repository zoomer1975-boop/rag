"""GraphRAGRetriever — LightRAG 스타일 dual-level 그래프 검색.

쿼리에서 LLM으로 low/high level 키워드를 추출하고,
 - low: entities 테이블 pgvector 유사도 검색
 - high: relationships 테이블 pgvector 유사도 검색
을 수행한다. 검색된 엔티티 기준 1-hop 이웃(관계·엔티티)을 확장하고,
엔티티/관계의 source_chunk_ids 를 union 하여 반환한다.

LLM/파싱 실패 시에는 전체 질의를 low-level 키워드로 fallback 하여
검색은 계속 진행한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.json_parsing import parse_json_object
from app.services.llm import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You extract search keywords from a user query for a knowledge-graph RAG system. "
    "Respond with a single JSON object ONLY, no prose, no markdown. "
    'Schema: {"low_level_keywords": [str], "high_level_keywords": [str]}. '
    "low_level_keywords: concrete entities, proper nouns, specific terms. "
    "high_level_keywords: abstract themes, relations, topics."
)


@dataclass(frozen=True)
class RetrievedEntity:
    id: int
    name: str
    entity_type: str
    description: str
    source_chunk_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class RetrievedRelationship:
    id: int
    source_entity_id: int
    target_entity_id: int
    description: str
    keywords: tuple[str, ...] = ()
    weight: float = 1.0
    source_chunk_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class GraphRetrievalResult:
    entities: tuple[RetrievedEntity, ...] = ()
    relationships: tuple[RetrievedRelationship, ...] = ()
    chunk_ids: tuple[int, ...] = ()


_EMPTY = GraphRetrievalResult()


class GraphRAGRetriever:
    def __init__(
        self,
        db: AsyncSession,
        embedding_client: EmbeddingClient | None = None,
        llm_client: LLMClient | None = None,
        *,
        top_k_entities: int | None = None,
        top_k_relationships: int | None = None,
        neighbor_hops: int | None = None,
    ) -> None:
        settings = get_settings()
        self._db = db
        self._embeddings = embedding_client or get_embedding_client()
        self._llm = llm_client or get_llm_client()
        self._top_k_entities = (
            top_k_entities if top_k_entities is not None else settings.graph_top_k_entities
        )
        self._top_k_relationships = (
            top_k_relationships
            if top_k_relationships is not None
            else settings.graph_top_k_relationships
        )
        self._neighbor_hops = (
            neighbor_hops if neighbor_hops is not None else settings.graph_neighbor_hops
        )

    async def retrieve(self, query: str, tenant_id: int) -> GraphRetrievalResult:
        if not query or not query.strip():
            return _EMPTY

        low_keywords, high_keywords = await self._extract_keywords(query)

        # 모든 레벨이 비면 전체 질의를 low-level 로 fallback
        if not low_keywords and not high_keywords:
            low_keywords = [query.strip()]

        entities = await self._search_entities(low_keywords, tenant_id)
        relationships = await self._search_relationships(high_keywords, tenant_id)

        entity_map: dict[int, Entity] = {e.id: e for e in entities}
        relationship_map: dict[int, Relationship] = {r.id: r for r in relationships}

        if self._neighbor_hops > 0 and entity_map:
            expanded_rels = await self._expand_relationships_from_entities(
                list(entity_map.keys()), tenant_id
            )
            for rel in expanded_rels:
                relationship_map.setdefault(rel.id, rel)

        # 관계의 양 끝 엔티티를 이웃으로 추가
        missing_ids: set[int] = set()
        for rel in relationship_map.values():
            if rel.source_entity_id not in entity_map:
                missing_ids.add(rel.source_entity_id)
            if rel.target_entity_id not in entity_map:
                missing_ids.add(rel.target_entity_id)

        if missing_ids:
            neighbors = await self._fetch_entities_by_ids(list(missing_ids), tenant_id)
            for ent in neighbors:
                entity_map.setdefault(ent.id, ent)

        chunk_ids = _collect_chunk_ids(
            list(entity_map.values()), list(relationship_map.values())
        )

        return GraphRetrievalResult(
            entities=tuple(_to_retrieved_entity(e) for e in entity_map.values()),
            relationships=tuple(
                _to_retrieved_relationship(r) for r in relationship_map.values()
            ),
            chunk_ids=tuple(chunk_ids),
        )

    async def _extract_keywords(self, query: str) -> tuple[list[str], list[str]]:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extract keywords from the following query. Return JSON only.\n\n"
                    f"Query: {query}"
                ),
            },
        ]

        try:
            raw = await self._llm.chat(messages=messages, temperature=0.0)
        except Exception as exc:
            logger.warning("graph_retriever: LLM call failed: %s", exc)
            return [], []

        payload = parse_json_object(raw)
        if payload is None:
            logger.warning("graph_retriever: failed to parse keyword JSON")
            return [], []

        low = _coerce_str_list(payload.get("low_level_keywords"))
        high = _coerce_str_list(payload.get("high_level_keywords"))
        return low, high

    async def _search_entities(
        self, keywords: list[str], tenant_id: int
    ) -> list[Entity]:
        if not keywords:
            return []
        text = " ".join(keywords).strip()
        if not text:
            return []
        vec = await self._embeddings.embed(text)
        stmt = (
            select(Entity)
            .where(
                Entity.tenant_id == tenant_id,
                Entity.description_embedding.is_not(None),
            )
            .order_by(Entity.description_embedding.cosine_distance(vec))
            .limit(self._top_k_entities)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _search_relationships(
        self, keywords: list[str], tenant_id: int
    ) -> list[Relationship]:
        if not keywords:
            return []
        text = " ".join(keywords).strip()
        if not text:
            return []
        vec = await self._embeddings.embed(text)
        stmt = (
            select(Relationship)
            .where(
                Relationship.tenant_id == tenant_id,
                Relationship.description_embedding.is_not(None),
            )
            .order_by(Relationship.description_embedding.cosine_distance(vec))
            .limit(self._top_k_relationships)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _expand_relationships_from_entities(
        self, entity_ids: list[int], tenant_id: int
    ) -> list[Relationship]:
        if not entity_ids:
            return []
        stmt = select(Relationship).where(
            Relationship.tenant_id == tenant_id,
            or_(
                Relationship.source_entity_id.in_(entity_ids),
                Relationship.target_entity_id.in_(entity_ids),
            ),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_entities_by_ids(
        self, ids: list[int], tenant_id: int
    ) -> list[Entity]:
        if not ids:
            return []
        stmt = select(Entity).where(
            Entity.tenant_id == tenant_id,
            Entity.id.in_(ids),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())


def _coerce_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
    return out


def _collect_chunk_ids(
    entities: list[Entity], relationships: list[Relationship]
) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for ent in entities:
        for cid in ent.source_chunk_ids or ():
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
    for rel in relationships:
        for cid in rel.source_chunk_ids or ():
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
    return ordered


def _to_retrieved_entity(e: Entity) -> RetrievedEntity:
    return RetrievedEntity(
        id=e.id,
        name=e.name,
        entity_type=e.entity_type,
        description=e.description or "",
        source_chunk_ids=tuple(e.source_chunk_ids or ()),
    )


def _to_retrieved_relationship(r: Relationship) -> RetrievedRelationship:
    return RetrievedRelationship(
        id=r.id,
        source_entity_id=r.source_entity_id,
        target_entity_id=r.target_entity_id,
        description=r.description or "",
        keywords=tuple(r.keywords or ()),
        weight=float(r.weight),
        source_chunk_ids=tuple(r.source_chunk_ids or ()),
    )
