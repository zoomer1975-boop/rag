"""GraphExtractor — LLM으로 청크에서 엔티티/관계를 추출.

LightRAG 스타일 프롬프트로 `{entities, relationships}` JSON을 받아
immutable dataclass로 변환한다. LLM 호출 실패·JSON 파싱 실패 시에는
예외를 던지지 않고 빈 결과를 반환해 인제스트 파이프라인이
청크 저장까지는 성공하도록 허용한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.json_parsing import parse_json_object
from app.services.llm import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


_DEFAULT_WEIGHT = 1.0
_SYSTEM_PROMPT = (
    "You extract a knowledge graph from text chunks. "
    "Respond with a single JSON object ONLY, no prose, no markdown. "
    'Schema: {"entities": [{"name": str, "type": str, "description": str}], '
    '"relationships": [{"source": str, "target": str, "description": str, '
    '"keywords": [str], "weight": float}]}. '
    "'source' and 'target' must exactly match an entity 'name'. "
    "'weight' is 0.0–1.0 confidence. Use lowercase entity types like "
    "person, organization, location, concept, event."
)


@dataclass(frozen=True)
class ExtractedEntity:
    name: str
    entity_type: str
    description: str = ""


@dataclass(frozen=True)
class ExtractedRelationship:
    source: str
    target: str
    description: str
    keywords: tuple[str, ...] = ()
    weight: float = _DEFAULT_WEIGHT


@dataclass(frozen=True)
class ExtractionResult:
    entities: tuple[ExtractedEntity, ...] = ()
    relationships: tuple[ExtractedRelationship, ...] = ()


_EMPTY = ExtractionResult()


class GraphExtractor:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or get_llm_client()

    async def extract(self, text: str) -> ExtractionResult:
        if not text or not text.strip():
            return _EMPTY

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extract the knowledge graph from the following chunk. "
                    "Return JSON only.\n\n---\n" + text
                ),
            },
        ]

        try:
            raw = await self._llm.chat(messages=messages, temperature=0.0)
        except Exception as exc:  # LLM 장애를 전체 인제스트 실패로 확장하지 않는다
            logger.warning("graph_extractor: LLM call failed: %s", exc)
            return _EMPTY

        payload = parse_json_object(raw)
        if payload is None:
            logger.warning("graph_extractor: failed to parse JSON from LLM output")
            return _EMPTY

        entities = _coerce_entities(payload.get("entities"))
        relationships = _coerce_relationships(payload.get("relationships"), entities)
        return ExtractionResult(entities=entities, relationships=relationships)


def _coerce_entities(raw: Any) -> tuple[ExtractedEntity, ...]:
    if not isinstance(raw, list):
        return ()

    seen: set[tuple[str, str]] = set()
    result: list[ExtractedEntity] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _clean_str(item.get("name"))
        entity_type = _clean_str(item.get("type") or item.get("entity_type"))
        if not name or not entity_type:
            continue
        key = (name.lower(), entity_type.lower())
        if key in seen:
            continue
        seen.add(key)
        description = _clean_str(item.get("description"))
        result.append(
            ExtractedEntity(
                name=name,
                entity_type=entity_type.lower(),
                description=description,
            )
        )
    return tuple(result)


def _coerce_relationships(
    raw: Any, entities: tuple[ExtractedEntity, ...]
) -> tuple[ExtractedRelationship, ...]:
    if not isinstance(raw, list):
        return ()

    known = {e.name for e in entities}
    result: list[ExtractedRelationship] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = _clean_str(item.get("source"))
        target = _clean_str(item.get("target"))
        if not source or not target:
            continue
        if source not in known or target not in known:
            continue
        description = _clean_str(item.get("description"))
        keywords = _coerce_keywords(item.get("keywords"))
        weight = _coerce_weight(item.get("weight"))
        result.append(
            ExtractedRelationship(
                source=source,
                target=target,
                description=description,
                keywords=keywords,
                weight=weight,
            )
        )
    return tuple(result)


def _coerce_keywords(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    cleaned = [_clean_str(k) for k in raw]
    return tuple(k for k in cleaned if k)


def _coerce_weight(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_WEIGHT
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _clean_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def get_graph_extractor() -> GraphExtractor:
    return GraphExtractor()
