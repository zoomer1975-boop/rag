"""Cross-encoder reranker — GraphRAG 검색 결과를 LLM 전달 전에 재순위."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_instance: RerankerService | None = None


class RerankerService:
    def __init__(self, model_name: str, device: str) -> None:
        from sentence_transformers import CrossEncoder

        logger.info("reranker: loading model=%s device=%s", model_name, device)
        self._model = CrossEncoder(model_name, device=device)
        self._model_name = model_name
        logger.info("reranker: model loaded")

    def _compute(self, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        pairs = [[query, chunk["content"]] for chunk in chunks]
        scores = self._model.predict(pairs, apply_softmax=True)
        logger.debug("reranker: raw_scores=%s", scores.tolist())
        ranked = sorted(zip(scores, chunks), key=lambda x: float(x[0]), reverse=True)
        return [
            {**{k: v for k, v in chunk.items() if k != "score"}, "score": float(score)}
            for score, chunk in ranked[:top_n]
        ]

    async def rerank(self, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        if not chunks:
            return chunks
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._compute, query, chunks, top_n)
        score_summary = " | ".join(
            f"[{i+1}] {c['score']:.4f}"
            for i, c in enumerate(result)
        )
        logger.info(
            "reranker: query_len=%d input=%d output=%d scores=[ %s ]",
            len(query),
            len(chunks),
            len(result),
            score_summary,
        )
        return result


@lru_cache(maxsize=1)
def _load_reranker(model_name: str, device: str) -> RerankerService:
    return RerankerService(model_name=model_name, device=device)


def get_reranker_service() -> RerankerService | None:
    from app.config import get_settings

    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    svc = _load_reranker(settings.reranker_model, settings.reranker_device)
    logger.info("get_reranker_service: returning %r cache_info=%s", svc, _load_reranker.cache_info())
    return svc
