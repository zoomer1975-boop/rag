"""상용문구 제거 서비스 — 인제스트 파이프라인에서 등록된 패턴을 본문에서 제거합니다."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boilerplate_pattern import BoilerplatePattern

logger = logging.getLogger(__name__)

_MAX_PATTERN_LEN = 2000
_MAX_PATTERNS_PER_TENANT = 100

# 중첩 quantifier ReDoS 휴리스틱
_REDOS_RE = re.compile(r"(\(\?[^)]*\))?[\w\s]*[+*]\)?[+*?]")


@dataclass
class _CompiledPattern:
    id: int
    kind: Literal["literal", "regex"]
    value: str | re.Pattern


async def load_patterns(db: AsyncSession, tenant_id: int) -> list[_CompiledPattern]:
    """DB에서 활성 패턴을 로드하고 regex는 컴파일하여 반환합니다."""
    result = await db.execute(
        select(BoilerplatePattern)
        .where(
            BoilerplatePattern.tenant_id == tenant_id,
            BoilerplatePattern.is_active == True,  # noqa: E712
        )
        .order_by(BoilerplatePattern.sort_order, BoilerplatePattern.id)
    )
    rows = result.scalars().all()

    compiled: list[_CompiledPattern] = []
    for row in rows:
        if row.pattern_type == "literal":
            compiled.append(_CompiledPattern(id=row.id, kind="literal", value=row.pattern))
        else:
            try:
                compiled.append(
                    _CompiledPattern(id=row.id, kind="regex", value=re.compile(row.pattern))
                )
            except re.error as exc:
                logger.warning(
                    "보일러플레이트 패턴 컴파일 실패 (id=%d, pattern=%r): %s — 건너뜁니다.",
                    row.id,
                    row.pattern,
                    exc,
                )
    return compiled


def apply(text: str, patterns: list[_CompiledPattern]) -> str:
    """등록된 패턴을 텍스트에서 제거하고 연속된 빈 줄을 정리합니다."""
    if not patterns:
        return text

    for p in patterns:
        try:
            if p.kind == "literal":
                text = text.replace(p.value, "")
            else:
                text = p.value.sub("", text)
        except Exception as exc:
            logger.warning("보일러플레이트 패턴 적용 오류 (id=%d): %s — 건너뜁니다.", p.id, exc)

    # 연속된 3개 이상의 빈 줄을 2개로 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def validate_pattern(pattern_type: str, pattern: str) -> str | None:
    """패턴 유효성 검사. 오류가 있으면 오류 메시지를 반환합니다."""
    if len(pattern) > _MAX_PATTERN_LEN:
        return f"패턴 길이는 {_MAX_PATTERN_LEN}자를 초과할 수 없습니다."
    if not pattern.strip():
        return "패턴은 빈 문자열일 수 없습니다."

    if pattern_type == "regex":
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"올바르지 않은 정규식입니다: {exc}"
        if _REDOS_RE.search(pattern):
            return "잠재적 ReDoS 위험이 있는 중첩 quantifier 패턴은 사용할 수 없습니다."

    return None
