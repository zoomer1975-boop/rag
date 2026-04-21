"""명확화 질문 서비스 — 모호한 쿼리에 대해 추가 질문을 생성한다."""

import json
import logging
from dataclasses import dataclass, field

from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

# 하이유리스틱 임계값
_MIN_TOKEN_COUNT = 4          # 이 미만이면 짧은 쿼리로 판단
_MAX_RETRIEVAL_SCORE = 0.55   # 최고 유사도 점수가 이 미만이면 컨텍스트 부족으로 판단
_MAX_QUESTIONS = 2            # 한 번에 생성할 최대 질문 수
_MAX_CLARIFICATION_ROUNDS = 2 # 연속 명확화 라운드 최대 횟수 (루프 방지)

_SYSTEM_PROMPT = """\
You are a helpful assistant that decides whether a user's question needs clarification.
Given a user query and optional retrieved document snippets, determine if asking 1-2 short
clarifying questions would significantly improve the answer quality.

Respond ONLY with valid JSON in this exact format:
{
  "needs_clarification": true | false,
  "questions": ["question 1", "question 2"]  // empty array if needs_clarification is false
}

Rules:
- Set needs_clarification=true only when the query is genuinely ambiguous or critically lacks context.
- Generate at most 2 questions; prefer 1 when possible.
- Questions must be short, specific, and in the same language as the user query.
- If the query is clear enough to answer reasonably, set needs_clarification=false.
- Never ask for information that is irrelevant to the query topic.
"""


@dataclass(frozen=True)
class ClarificationResult:
    needs_clarification: bool
    questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClarifierConfig:
    min_token_count: int = _MIN_TOKEN_COUNT
    max_retrieval_score: float = _MAX_RETRIEVAL_SCORE
    max_questions: int = _MAX_QUESTIONS
    max_rounds: int = _MAX_CLARIFICATION_ROUNDS


class ClarifierService:
    def __init__(self, llm: LLMClient | None = None, config: ClarifierConfig | None = None) -> None:
        self._llm = llm or LLMClient()
        self._config = config or ClarifierConfig()

    def _heuristic_gate(self, query: str, top_score: float | None) -> bool:
        """빠른 경량 게이트: True면 LLM 판단으로 넘어간다."""
        token_count = len(query.split())
        if token_count >= self._config.min_token_count:
            return False
        if top_score is not None and top_score >= self._config.max_retrieval_score:
            return False
        return True

    async def should_clarify(
        self,
        query: str,
        top_score: float | None = None,
        context_snippets: list[str] | None = None,
        clarification_round: int = 0,
    ) -> ClarificationResult:
        """쿼리가 명확화 질문이 필요한지 판단한다.

        Args:
            query: 사용자 쿼리 원문
            top_score: RAG 검색 최고 유사도 점수 (없으면 None)
            context_snippets: 검색된 문서 발췌 (최대 3개)
            clarification_round: 현재까지 명확화 라운드 수 (루프 방지용)

        Returns:
            ClarificationResult — needs_clarification과 questions 포함
        """
        if clarification_round >= self._config.max_rounds:
            return ClarificationResult(needs_clarification=False)

        if not self._heuristic_gate(query, top_score):
            return ClarificationResult(needs_clarification=False)

        return await self._llm_judge(query, context_snippets or [])

    async def _llm_judge(self, query: str, snippets: list[str]) -> ClarificationResult:
        """LLM에게 명확화 필요 여부를 JSON으로 판단받는다."""
        snippet_text = ""
        if snippets:
            joined = "\n---\n".join(snippets[:3])
            snippet_text = f"\n\nRetrieved context snippets:\n{joined}"

        user_message = f"User query: {query}{snippet_text}"

        try:
            raw = await self._llm.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=256,
            )
            result = json.loads(raw)
            needs = bool(result.get("needs_clarification", False))
            questions: list[str] = result.get("questions", [])
            if not isinstance(questions, list):
                questions = []
            questions = [q for q in questions if isinstance(q, str) and q.strip()]
            questions = questions[: self._config.max_questions]
            return ClarificationResult(needs_clarification=needs and bool(questions), questions=questions)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("clarifier LLM response parse error: %s", exc)
            return ClarificationResult(needs_clarification=False)
