"""Gemma4 vLLM thinking 토큰 제거 테스트"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── strip_thinking_tokens 단위 테스트 ─────────────────────────────────────────

class TestStripThinkingTokens:
    def test_removes_thinking_block(self):
        from app.services.llm import strip_thinking_tokens

        raw = "<|channel>thought\n재고를 확인해야 한다.\n<channel|>요청하신 장난감 목록입니다!"
        assert strip_thinking_tokens(raw) == "요청하신 장난감 목록입니다!"

    def test_no_thinking_block_unchanged(self):
        from app.services.llm import strip_thinking_tokens

        text = "안녕하세요, 무엇을 도와드릴까요?"
        assert strip_thinking_tokens(text) == text

    def test_multiline_thinking_content_removed(self):
        from app.services.llm import strip_thinking_tokens

        raw = (
            "<|channel>thought\n"
            "사용자가 장난감 재고를 묻고 있다.\n"
            "get_toy_inventory 툴을 사용해야 한다.\n"
            "결과를 정리해서 답해야 한다.\n"
            "<channel|>현재 재고는 다음과 같습니다: ..."
        )
        result = strip_thinking_tokens(raw)
        assert result == "현재 재고는 다음과 같습니다: ..."
        assert "<|channel>" not in result
        assert "<channel|>" not in result

    def test_empty_string_returns_empty(self):
        from app.services.llm import strip_thinking_tokens

        assert strip_thinking_tokens("") == ""

    def test_only_thinking_block_returns_empty(self):
        from app.services.llm import strip_thinking_tokens

        raw = "<|channel>thought\n생각중...\n<channel|>"
        assert strip_thinking_tokens(raw) == ""

    def test_newline_after_channel_end_stripped(self):
        from app.services.llm import strip_thinking_tokens

        raw = "<|channel>thought\n생각\n<channel|>\n실제 응답입니다."
        assert strip_thinking_tokens(raw) == "실제 응답입니다."


# ── chat() thinking 토큰 제거 테스트 ──────────────────────────────────────────

class TestChatStripsThinkingTokens:
    @pytest.mark.asyncio
    async def test_chat_strips_thinking_block_from_response(self):
        """chat()이 반환하는 content에서 thinking 블록이 제거되어야 한다."""
        from app.services.llm import LLMClient

        raw_content = "<|channel>thought\n생각중\n<channel|>최종 답변입니다."

        msg = MagicMock()
        msg.content = raw_content

        choice = MagicMock()
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            client = LLMClient()
            result = await client.chat(messages=[{"role": "user", "content": "test"}])

        assert result == "최종 답변입니다."
        assert "<|channel>" not in result


# ── chat_with_tools() TextResult thinking 토큰 제거 테스트 ────────────────────

class TestChatWithToolsStripsThinkingTokens:
    @pytest.mark.asyncio
    async def test_text_result_strips_thinking_block(self):
        """chat_with_tools()의 TextResult content에서 thinking 블록이 제거되어야 한다."""
        from app.services.llm import LLMClient, TextResult

        raw_content = (
            "<|channel>thought\n도구 결과를 정리해야 한다.\n<channel|>"
            "요청하신 장난감 목록입니다! 삐뽀삐뽀 구급차 5개가 있습니다."
        )

        msg = MagicMock()
        msg.tool_calls = None
        msg.content = raw_content

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            client = LLMClient()
            result = await client.chat_with_tools(
                messages=[{"role": "user", "content": "장난감 목록"}],
                tools=[{"type": "function", "function": {"name": "get_toy_inventory"}}],
            )

        assert isinstance(result, TextResult)
        assert "<|channel>" not in result.content
        assert "<channel|>" not in result.content
        assert "요청하신 장난감 목록입니다!" in result.content


# ── chat_stream() thinking 토큰 제거 테스트 ───────────────────────────────────

class TestChatStreamStripsThinkingTokens:
    @pytest.mark.asyncio
    async def test_stream_suppresses_thinking_block_tokens(self):
        """chat_stream()이 thinking 블록 내 토큰을 yield하지 않아야 한다."""
        from app.services.llm import LLMClient

        # 스트림 토큰 시뮬레이션: thinking 블록 + 실제 응답
        tokens = [
            "<|channel>thought\n",
            "이건 thinking 내용이라 사용자에게 보이면 안 된다.\n",
            "<channel|>",
            "실제 응답: 장난감 목록입니다.",
        ]

        def _make_chunk(content):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = content
            return chunk

        async def _fake_create(*args, **kwargs):
            async def _gen():
                for t in tokens:
                    yield _make_chunk(t)
            return _gen()

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            mock_openai.chat.completions.create = _fake_create

            client = LLMClient()
            collected = []
            async for token in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                collected.append(token)

        full_output = "".join(collected)
        assert "<|channel>" not in full_output
        assert "<channel|>" not in full_output
        assert "thinking 내용" not in full_output
        assert "실제 응답: 장난감 목록입니다." in full_output

    @pytest.mark.asyncio
    async def test_stream_no_thinking_tokens_yields_normally(self):
        """thinking 토큰이 없으면 스트림이 정상적으로 yield되어야 한다."""
        from app.services.llm import LLMClient

        tokens = ["안녕하세요, ", "무엇을 ", "도와드릴까요?"]

        def _make_chunk(content):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = content
            return chunk

        async def _fake_create(*args, **kwargs):
            async def _gen():
                for t in tokens:
                    yield _make_chunk(t)
            return _gen()

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            mock_openai.chat.completions.create = _fake_create

            client = LLMClient()
            collected = []
            async for token in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                collected.append(token)

        assert "".join(collected) == "".join(tokens)
