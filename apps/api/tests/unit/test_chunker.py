"""텍스트 청킹 서비스 단위 테스트 (TDD - RED 단계)"""

import pytest

from app.services.chunker import TextChunker


class TestTextChunker:
    def setup_method(self):
        self.chunker = TextChunker(chunk_size=500, chunk_overlap=50)

    # ─── 기본 청킹 ───────────────────────────────────────────────────────────

    def test_short_text_returns_single_chunk(self):
        text = "짧은 텍스트입니다."
        chunks = self.chunker.split(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits_into_multiple_chunks(self):
        text = "문장입니다. " * 200  # 충분히 긴 텍스트
        chunks = self.chunker.split(text)
        assert len(chunks) > 1

    def test_all_content_preserved(self):
        text = "단어 " * 300
        chunks = self.chunker.split(text)
        # 청크를 합쳤을 때 원본 단어가 모두 포함되어야 함 (overlap 제외)
        combined = " ".join(chunks)
        for word in text.strip().split():
            assert word in combined

    def test_chunk_size_not_exceeded(self):
        text = "테스트 문장입니다. " * 300
        chunks = self.chunker.split(text)
        for chunk in chunks:
            # 토큰 기준이지만 대략적으로 문자 수로 검증
            assert len(chunk) <= self.chunker.chunk_size * 10

    def test_empty_text_returns_empty_list(self):
        chunks = self.chunker.split("")
        assert chunks == []

    def test_whitespace_only_returns_empty_list(self):
        chunks = self.chunker.split("   \n\t  ")
        assert chunks == []

    # ─── 메타데이터 청킹 ─────────────────────────────────────────────────────

    def test_split_with_metadata_returns_dicts(self):
        text = "테스트 문장입니다. " * 100
        results = self.chunker.split_with_metadata(text, source_url="https://example.com")
        assert len(results) > 0
        for item in results:
            assert "content" in item
            assert "index" in item
            assert "source_url" in item
            assert item["source_url"] == "https://example.com"

    def test_chunk_indices_are_sequential(self):
        text = "문장 " * 200
        results = self.chunker.split_with_metadata(text)
        indices = [r["index"] for r in results]
        assert indices == list(range(len(results)))

    # ─── 다양한 크기 설정 ────────────────────────────────────────────────────

    def test_custom_chunk_size(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "단어 " * 500
        chunks = chunker.split(text)
        assert len(chunks) > TextChunker(chunk_size=500, chunk_overlap=50).split(text).__len__()
