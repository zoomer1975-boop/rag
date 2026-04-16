"""문서 검색 필터 단위 테스트 (TDD - RED 단계)"""

import pytest
from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.services.document_search import build_document_search_filter


# 테스트용 최소 Document stub (실제 ORM 연결 없음)
class _Base(DeclarativeBase):
    pass


class _FakeDoc(_Base):
    __tablename__ = "documents_test"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class TestBuildDocumentSearchFilter:
    """build_document_search_filter(model, q) 반환값이 올바른 SQL 조건을 생성하는지 확인."""

    def test_none_q_returns_none(self):
        """q가 None이면 None을 반환 — 쿼리에 where 조건이 추가되지 않아야 함."""
        result = build_document_search_filter(_FakeDoc, q=None)
        assert result is None

    def test_empty_string_returns_none(self):
        """q가 빈 문자열이면 None 반환."""
        result = build_document_search_filter(_FakeDoc, q="   ")
        assert result is None

    def test_non_empty_q_returns_condition(self):
        """q가 있으면 OR 조건 객체를 반환한다."""
        result = build_document_search_filter(_FakeDoc, q="python")
        assert result is not None

    def test_condition_includes_title_ilike(self):
        """반환된 조건의 SQL에 title ilike 가 포함된다."""
        condition = build_document_search_filter(_FakeDoc, q="FastAPI")
        sql = str(condition.compile(compile_kwargs={"literal_binds": True}))
        assert "title" in sql.lower()
        assert "fastapi" in sql.lower()

    def test_condition_includes_source_url_ilike(self):
        """반환된 조건의 SQL에 source_url ilike 가 포함된다."""
        condition = build_document_search_filter(_FakeDoc, q="example.com")
        sql = str(condition.compile(compile_kwargs={"literal_binds": True}))
        assert "source_url" in sql.lower()
        assert "example.com" in sql.lower()

    def test_search_is_case_insensitive(self):
        """검색은 대소문자를 구분하지 않는다 (ilike 사용)."""
        condition = build_document_search_filter(_FakeDoc, q="PyThOn")
        sql = str(condition.compile(compile_kwargs={"literal_binds": True}))
        # ilike 또는 LOWER() 패턴이 포함되어야 함
        assert "ilike" in sql.lower() or "lower" in sql.lower()

    def test_q_is_stripped_and_wildcarded(self):
        """q 앞뒤 공백을 제거하고 % wildcard로 감싼다."""
        condition = build_document_search_filter(_FakeDoc, q="  hello  ")
        sql = str(condition.compile(compile_kwargs={"literal_binds": True}))
        assert "%hello%" in sql.lower()
