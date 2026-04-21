"""Unit tests for ClarifierService."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.clarifier import ClarificationResult, ClarifierConfig, ClarifierService


class TestHeuristicGate:
    def setup_method(self) -> None:
        self.svc = ClarifierService(llm=AsyncMock())

    def test_short_query_low_score_passes_gate(self) -> None:
        # 3 tokens, score below threshold → gate opens
        assert self.svc._heuristic_gate("날씨 알려줘", top_score=0.3) is True

    def test_long_query_skips_gate(self) -> None:
        # 5+ tokens → gate closes regardless of score
        assert self.svc._heuristic_gate("서울 내일 날씨 어떻게 되나요", top_score=0.2) is False

    def test_high_score_skips_gate(self) -> None:
        # short but high retrieval score → gate closes
        assert self.svc._heuristic_gate("뭐야", top_score=0.8) is False

    def test_no_score_short_query_passes_gate(self) -> None:
        # no score available, short query → gate opens
        assert self.svc._heuristic_gate("뭐야", top_score=None) is True

    def test_exactly_min_tokens_skips_gate(self) -> None:
        # exactly min_token_count (4) → gate closes (>= check)
        assert self.svc._heuristic_gate("a b c d", top_score=0.1) is False


class TestShouldClarify:
    def setup_method(self) -> None:
        self.mock_llm = AsyncMock()
        self.svc = ClarifierService(llm=self.mock_llm)

    async def _set_llm_response(self, needs: bool, questions: list[str]) -> None:
        import json
        self.mock_llm.chat = AsyncMock(
            return_value=json.dumps({"needs_clarification": needs, "questions": questions})
        )

    @pytest.mark.asyncio
    async def test_long_query_returns_no_clarification_without_llm(self) -> None:
        result = await self.svc.should_clarify("서울 내일 날씨 어떻게 되나요", top_score=0.2)
        assert result.needs_clarification is False
        self.mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_rounds_prevents_clarification(self) -> None:
        result = await self.svc.should_clarify("뭐야", top_score=0.2, clarification_round=2)
        assert result.needs_clarification is False
        self.mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_returns_clarification(self) -> None:
        await self._set_llm_response(True, ["어떤 지역의 날씨인가요?"])
        result = await self.svc.should_clarify("날씨", top_score=0.2)
        assert result.needs_clarification is True
        assert len(result.questions) == 1

    @pytest.mark.asyncio
    async def test_questions_capped_at_max(self) -> None:
        await self._set_llm_response(True, ["q1", "q2", "q3", "q4"])
        result = await self.svc.should_clarify("뭐야", top_score=0.1)
        assert len(result.questions) <= 2

    @pytest.mark.asyncio
    async def test_llm_returns_no_clarification(self) -> None:
        await self._set_llm_response(False, [])
        result = await self.svc.should_clarify("날씨", top_score=0.2)
        assert result.needs_clarification is False
        assert result.questions == []

    @pytest.mark.asyncio
    async def test_malformed_json_returns_no_clarification(self) -> None:
        self.mock_llm.chat = AsyncMock(return_value="not valid json{{")
        result = await self.svc.should_clarify("뭐야", top_score=0.1)
        assert result.needs_clarification is False

    @pytest.mark.asyncio
    async def test_needs_true_but_empty_questions_returns_false(self) -> None:
        # LLM says needs=true but provides no questions → should be false
        await self._set_llm_response(True, [])
        result = await self.svc.should_clarify("뭐야", top_score=0.1)
        assert result.needs_clarification is False

    @pytest.mark.asyncio
    async def test_context_snippets_passed_to_llm(self) -> None:
        await self._set_llm_response(True, ["어떤 용도로 쓰실 건가요?"])
        await self.svc.should_clarify(
            "뭐야",
            top_score=0.1,
            context_snippets=["snippet A", "snippet B"],
        )
        call_args = self.mock_llm.chat.call_args
        user_content = call_args.kwargs["messages"][-1]["content"]
        assert "snippet A" in user_content


class TestClarifierConfig:
    def test_custom_config_applied(self) -> None:
        config = ClarifierConfig(min_token_count=6, max_retrieval_score=0.7, max_questions=1, max_rounds=1)
        svc = ClarifierService(llm=AsyncMock(), config=config)
        # 5 tokens is less than 6 → gate opens
        assert svc._heuristic_gate("a b c d e", top_score=0.1) is True
        # score 0.65 < 0.7 → still open
        assert svc._heuristic_gate("a b c", top_score=0.65) is True
        # score 0.75 >= 0.7 → gate closes
        assert svc._heuristic_gate("a b c", top_score=0.75) is False
