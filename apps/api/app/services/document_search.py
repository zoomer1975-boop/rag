"""문서 검색 필터 빌더"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_


def build_document_search_filter(model: Any, q: str | None):
    """title 또는 source_url에 대한 ILIKE 검색 조건을 반환합니다.

    Args:
        model: Document ORM 모델 (또는 title/source_url 컬럼을 가진 모델).
        q: 검색어. None이거나 공백만 있으면 None 반환.

    Returns:
        SQLAlchemy OR 조건 또는 None.
    """
    if not q or not q.strip():
        return None

    term = f"%{q.strip().lower()}%"
    return or_(
        model.title.ilike(term),
        model.source_url.ilike(term),
    )
