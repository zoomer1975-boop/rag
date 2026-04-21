"""GraphStore — 추출된 엔티티/관계를 Postgres에 UPSERT + 병합.

엔티티는 (tenant_id, lower(name), entity_type) 기준으로 병합한다.
- 기존 엔티티가 있으면 description 을 이어붙이고 source_chunk_ids 를 누적한다.
- 관계는 (tenant_id, source_entity_id, target_entity_id) 기준으로 병합한다.

UNIQUE 제약은 raw name 에만 걸려 있으므로 병합 단계에서 SELECT lower(name)
쿼리로 먼저 조회하고, 없으면 INSERT 한다. 경쟁이 극히 드물고 인제스트 파이프라인은
청크 단위 순차 처리이므로 이 경로는 충분히 안전하다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.relationship import Relationship
from app.services.embeddings import EmbeddingClient
from app.services.graph_extractor import (
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EntityChange:
    entity: Entity
    description_changed: bool


class GraphStore:
    def __init__(self, db: AsyncSession, embedding_client: EmbeddingClient) -> None:
        self._db = db
        self._embeddings = embedding_client

    async def upsert(
        self,
        tenant_id: int,
        chunk_id: int,
        extraction: ExtractionResult,
    ) -> None:
        if not extraction.entities and not extraction.relationships:
            return

        entity_changes = await self._upsert_entities(
            tenant_id=tenant_id,
            chunk_id=chunk_id,
            entities=extraction.entities,
        )

        rel_changes = await self._upsert_relationships(
            tenant_id=tenant_id,
            chunk_id=chunk_id,
            relationships=extraction.relationships,
            name_to_entity={e.entity.name: e.entity for e in entity_changes},
        )

        await self._embed_changes(entity_changes, rel_changes)

        await self._db.commit()

    async def _upsert_entities(
        self,
        tenant_id: int,
        chunk_id: int,
        entities: Sequence[ExtractedEntity],
    ) -> list[_EntityChange]:
        if not entities:
            return []

        changes: list[_EntityChange] = []
        for extracted in entities:
            existing = await self._find_entity(
                tenant_id=tenant_id,
                name=extracted.name,
                entity_type=extracted.entity_type,
            )
            if existing is None:
                row = Entity(
                    tenant_id=tenant_id,
                    name=extracted.name,
                    entity_type=extracted.entity_type,
                    description=extracted.description,
                    source_chunk_ids=[chunk_id],
                )
                self._db.add(row)
                await self._db.flush()
                changes.append(_EntityChange(entity=row, description_changed=True))
                continue

            description_changed = False
            if extracted.description and extracted.description not in existing.description:
                existing.description = _merge_descriptions(
                    existing.description, extracted.description
                )
                description_changed = True

            existing.source_chunk_ids = _append_unique(existing.source_chunk_ids, chunk_id)
            changes.append(
                _EntityChange(entity=existing, description_changed=description_changed)
            )

        await self._db.flush()
        return changes

    async def _find_entity(
        self, tenant_id: int, name: str, entity_type: str
    ) -> Entity | None:
        stmt = select(Entity).where(
            Entity.tenant_id == tenant_id,
            func.lower(Entity.name) == name.lower(),
            Entity.entity_type == entity_type,
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def _upsert_relationships(
        self,
        tenant_id: int,
        chunk_id: int,
        relationships: Sequence[ExtractedRelationship],
        name_to_entity: dict[str, Entity],
    ) -> list[_EntityChange]:
        if not relationships:
            return []

        changes: list[_EntityChange] = []
        lower_index = {name.lower(): ent for name, ent in name_to_entity.items()}

        for rel in relationships:
            source = lower_index.get(rel.source.lower()) or await self._find_entity(
                tenant_id=tenant_id, name=rel.source, entity_type=""
            )
            target = lower_index.get(rel.target.lower()) or await self._find_entity(
                tenant_id=tenant_id, name=rel.target, entity_type=""
            )
            if source is None or target is None:
                logger.debug(
                    "graph_store: skipping dangling relationship %s→%s",
                    rel.source,
                    rel.target,
                )
                continue

            existing = await self._find_relationship(
                tenant_id=tenant_id,
                source_id=source.id,
                target_id=target.id,
            )
            if existing is None:
                row = Relationship(
                    tenant_id=tenant_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    description=rel.description,
                    keywords=list(rel.keywords),
                    weight=rel.weight,
                    source_chunk_ids=[chunk_id],
                )
                self._db.add(row)
                await self._db.flush()
                changes.append(_EntityChange(entity=row, description_changed=True))
                continue

            description_changed = False
            if rel.description and rel.description not in existing.description:
                existing.description = _merge_descriptions(
                    existing.description, rel.description
                )
                description_changed = True

            if rel.keywords:
                existing.keywords = _merge_keywords(existing.keywords, rel.keywords)
            existing.weight = max(existing.weight, rel.weight)
            existing.source_chunk_ids = _append_unique(
                existing.source_chunk_ids, chunk_id
            )
            changes.append(
                _EntityChange(entity=existing, description_changed=description_changed)
            )

        await self._db.flush()
        return changes

    async def _find_relationship(
        self, tenant_id: int, source_id: int, target_id: int
    ) -> Relationship | None:
        stmt = select(Relationship).where(
            Relationship.tenant_id == tenant_id,
            Relationship.source_entity_id == source_id,
            Relationship.target_entity_id == target_id,
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def _embed_changes(
        self,
        entity_changes: Iterable[_EntityChange],
        rel_changes: Iterable[_EntityChange],
    ) -> None:
        rows_to_embed: list[Entity | Relationship] = []
        texts: list[str] = []

        for change in entity_changes:
            if not change.description_changed:
                continue
            text = change.entity.description or change.entity.name
            rows_to_embed.append(change.entity)
            texts.append(text)

        for change in rel_changes:
            if not change.description_changed:
                continue
            text = change.entity.description or ""
            if not text:
                continue
            rows_to_embed.append(change.entity)
            texts.append(text)

        if not texts:
            return

        embeddings = await self._embeddings.embed_batch(texts)
        for row, vec in zip(rows_to_embed, embeddings):
            row.description_embedding = vec


def _merge_descriptions(existing: str, new: str) -> str:
    existing = (existing or "").strip()
    new = (new or "").strip()
    if not existing:
        return new
    if not new:
        return existing
    return f"{existing}\n{new}"


def _merge_keywords(existing: list[str], new: tuple[str, ...]) -> list[str]:
    seen: dict[str, None] = {k: None for k in existing}
    for k in new:
        if k and k not in seen:
            seen[k] = None
    return list(seen.keys())


def _append_unique(existing: list[int] | None, value: int) -> list[int]:
    current = list(existing or [])
    if value in current:
        return current
    current.append(value)
    return current
