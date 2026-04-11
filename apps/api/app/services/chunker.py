"""텍스트 청킹 서비스 — 토큰 기반 슬라이딩 윈도우"""

import re

import tiktoken


class TextChunker:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._encoder = tiktoken.get_encoding("cl100k_base")

    def split(self, text: str) -> list[str]:
        """텍스트를 청크 리스트로 분할합니다."""
        text = text.strip()
        if not text:
            return []

        tokens = self._encoder.encode(text)

        if len(tokens) <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self._encoder.decode(chunk_tokens)
            chunks.append(chunk_text)

            if end == len(tokens):
                break
            start += self.chunk_size - self.chunk_overlap

        return chunks

    def split_with_metadata(self, text: str, **metadata) -> list[dict]:
        """청크 텍스트와 메타데이터를 함께 반환합니다."""
        chunks = self.split(text)
        return [
            {"content": chunk, "index": i, **metadata}
            for i, chunk in enumerate(chunks)
        ]
