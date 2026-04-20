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

_MAX_PATTERN_LEN = 10000
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
    logger.debug("보일러플레이트 패턴 로드: tenant_id=%d, 활성=%d", tenant_id, len(compiled))
    return compiled


def _literal_to_whitespace_regex(literal: str) -> re.Pattern:
    """리터럴 패턴을 공백 정규화 매칭 정규식으로 변환합니다.

    Jina Reader 등이 줄바꿈을 삽입해 문구가 여러 줄에 걸쳐 있어도 매칭되도록
    단어 사이의 공백을 \\s+ 로 치환합니다.
    """
    words = literal.split()
    if not words:
        return re.compile(re.escape(literal))
    return re.compile(r"\s+".join(re.escape(w) for w in words))


def apply(text: str, patterns: list[_CompiledPattern]) -> str:
    """등록된 패턴을 텍스트에서 제거하고 연속된 빈 줄을 정리합니다."""
    if not patterns:
        return text

    original_len = len(text)
    for p in patterns:
        try:
            if p.kind == "literal":
                # 1단계: 정확한 문자열 매칭
                text = text.replace(p.value, "")
                # 2단계: 공백 정규화 매칭 — Jina 등이 줄바꿈을 삽입한 경우 대응
                text = _literal_to_whitespace_regex(p.value).sub("", text)
            else:
                text = p.value.sub("", text)
        except Exception as exc:
            logger.warning("보일러플레이트 패턴 적용 오류 (id=%d): %s — 건너뜁니다.", p.id, exc)

    removed = original_len - len(text)
    if removed:
        logger.info("보일러플레이트 제거 완료: 총 %d bytes 제거됨", removed)

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
