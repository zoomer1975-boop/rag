"""Tool Calling 흐름 통합 테스트 — LLM mock 사용"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.llm import TextResult, ToolCallResult
from app.services.tool_executor import MAX_TOOL_CALLS_PER_CHAT, build_openai_tools


def _make_tool_call(tc_id: str, name: str, arguments: dict):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_tool_call_result(name: str, arguments: dict, tc_id: str = "tc_001"):
    tc = _make_tool_call(tc_id, name, arguments)
    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": tc_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}],
    }
    return ToolCallResult(tool_calls=[tc], assistant_message=assistant_msg)


class TestBuildOpenaiTools:
    """build_openai_tools의 기본 동작 검증"""

    def test_empty_list_returns_empty(self):
        assert build_openai_tools([]) == []

    def test_active_tool_included(self):
        tool = MagicMock()
        tool.name = "my_tool"
        tool.description = "desc"
        tool.is_active = True
        tool.url_template = "https://example.com/api"
        tool.query_params_schema = None
        tool.body_schema = None
        result = build_openai_tools([tool])
        assert len(result) == 1
        assert result[0]["function"]["name"] == "my_tool"


class TestStreamingHeaders:
    """SSE 응답 헤더 검증"""

    def test_x_accel_buffering_header_present(self):
        """StreamingResponse에 X-Accel-Buffering: no 헤더가 있어야 nginx 버퍼링이 비활성화된다."""
        import inspect
        import ast
        import textwrap
        from pathlib import Path

        source = Path("app/routers/chat.py").read_text(encoding="utf-8")
        assert "X-Accel-Buffering" in source, (
            "chat.py StreamingResponse headers에 'X-Accel-Buffering: no'가 없습니다. "
            "nginx proxy_buffering 설정만으로는 부족하며, 응답 헤더에도 명시해야 합니다."
        )


class TestToolCallingLoop:
    """_stream_response의 tool calling 루프 동작 검증"""

    @pytest.mark.asyncio
    async def test_no_tools_uses_streaming(self):
        """tool이 없으면 기존 스트리밍 경로를 사용한다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        async def _fake_stream(messages):
            yield "Hello"
            yield " world"
        llm_client.chat_stream = _fake_stream

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        events = []
        with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
            async for event in _stream_response(
                llm_client=llm_client,
                messages=[{"role": "user", "content": "hi"}],
                sources=[],
                conversation_id=1,
                session_id="s1",
                ls_logger=ls_logger,
                ls_run_id=None,
                ls_llm_run_id=None,
                openai_tools=None,
                tool_map=None,
            ):
                events.append(event)

        token_events = [e for e in events if '"token"' in e]
        assert len(token_events) == 2
        done_events = [e for e in events if '"done"' in e]
        assert len(done_events) == 1

    @pytest.mark.asyncio
    async def test_tool_call_executes_and_continues(self):
        """LLM이 tool_call을 반환하면 tool을 실행하고 최종 텍스트 응답을 스트리밍한다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        tool_call_result = _make_tool_call_result("get_weather", {"city": "Seoul"})
        text_result = TextResult(content="서울의 현재 기온은 25°C입니다.")

        llm_client.chat_with_tools = AsyncMock(side_effect=[tool_call_result, text_result])

        fake_tool = MagicMock()
        fake_tool.name = "get_weather"
        fake_tool.is_active = True

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        events = []
        with patch("app.routers.chat.execute_tool", new_callable=AsyncMock, return_value="[HTTP 200]\n{\"temp\": 25}"):
            with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
                async for event in _stream_response(
                    llm_client=llm_client,
                    messages=[{"role": "user", "content": "서울 날씨"}],
                    sources=[],
                    conversation_id=1,
                    session_id="s1",
                    ls_logger=ls_logger,
                    ls_run_id=None,
                    ls_llm_run_id=None,
                    openai_tools=[{"type": "function", "function": {"name": "get_weather"}}],
                    tool_map={"get_weather": fake_tool},
                ):
                    events.append(event)

        event_types = [json.loads(e[len("data: "):])["type"] for e in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "token" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_tool_text_result_streams_tokens(self):
        """tool path에서 TextResult를 받으면 LLM 재호출 없이 content를 단어 단위로 스트리밍해야 한다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        tool_call_result = _make_tool_call_result("get_weather", {"city": "Seoul"})
        # TextResult에 3단어 포함 → 최소 2개 이상의 token 이벤트 예상
        text_result = TextResult(content="서울의 현재 기온은")
        llm_client.chat_with_tools = AsyncMock(side_effect=[tool_call_result, text_result])
        # chat_stream은 호출되지 않아야 함 (LLM 재호출 없이 fake streaming)
        llm_client.chat_stream = AsyncMock(side_effect=AssertionError("chat_stream이 호출되면 안 됩니다"))

        fake_tool = MagicMock()
        fake_tool.name = "get_weather"

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        events = []
        with patch("app.routers.chat.execute_tool", new_callable=AsyncMock, return_value="[HTTP 200]\n{\"temp\": 25}"):
            with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
                async for event in _stream_response(
                    llm_client=llm_client,
                    messages=[{"role": "user", "content": "서울 날씨"}],
                    sources=[],
                    conversation_id=1,
                    session_id="s1",
                    ls_logger=ls_logger,
                    ls_run_id=None,
                    ls_llm_run_id=None,
                    openai_tools=[{"type": "function", "function": {"name": "get_weather"}}],
                    tool_map={"get_weather": fake_tool},
                ):
                    events.append(event)

        token_events = [json.loads(e[len("data: "):]) for e in events if '"token"' in e]
        # "서울의 현재 기온은" → 3단어 → 3개의 token 이벤트
        assert len(token_events) >= 2, (
            f"tool TextResult 경로에서 token 이벤트가 {len(token_events)}개입니다. "
            "content를 단어 단위로 나눠 스트리밍해야 합니다."
        )
        # 전체 내용이 누락 없이 전달됐는지 검증
        full_text = "".join(e["content"] for e in token_events)
        assert "서울의" in full_text and "기온은" in full_text

    @pytest.mark.asyncio
    async def test_max_tool_calls_uses_chat_for_final_response(self):
        """tool 호출이 MAX_TOOL_CALLS_PER_CHAT 횟수를 초과하면 chat()으로 최종 응답을 받는다.

        tool history가 있는 current_messages를 chat_stream에 tools 없이 보내면
        vLLM/Ollama가 오류를 낼 수 있으므로 안정적인 chat()을 사용한다.
        """
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        llm_client.chat_with_tools = AsyncMock(
            return_value=_make_tool_call_result("get_weather", {"city": "Seoul"})
        )
        llm_client.chat = AsyncMock(return_value="강제 종료 응답")
        # chat_stream은 호출되지 않아야 함
        llm_client.chat_stream = AsyncMock(side_effect=AssertionError("max 초과 시 chat_stream 호출 금지"))

        fake_tool = MagicMock()
        fake_tool.name = "get_weather"

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        with patch("app.routers.chat.execute_tool", new_callable=AsyncMock, return_value="[HTTP 200]\nok"):
            with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
                events = []
                async for event in _stream_response(
                    llm_client=llm_client,
                    messages=[{"role": "user", "content": "날씨"}],
                    sources=[],
                    conversation_id=1,
                    session_id="s1",
                    ls_logger=ls_logger,
                    ls_run_id=None,
                    ls_llm_run_id=None,
                    openai_tools=[{"type": "function"}],
                    tool_map={"get_weather": fake_tool},
                ):
                    events.append(event)

        assert llm_client.chat_with_tools.call_count == MAX_TOOL_CALLS_PER_CHAT
        assert llm_client.chat.call_count == 1, "max 초과 시 chat()으로 최종 응답을 받아야 합니다."

    @pytest.mark.asyncio
    async def test_max_tool_calls_enforced(self):
        """tool 호출이 MAX_TOOL_CALLS_PER_CHAT 횟수를 초과하면 강제 종료한다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        llm_client.chat_with_tools = AsyncMock(
            return_value=_make_tool_call_result("get_weather", {"city": "Seoul"})
        )
        llm_client.chat = AsyncMock(return_value="강제 종료 응답")

        fake_tool = MagicMock()
        fake_tool.name = "get_weather"

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        with patch("app.routers.chat.execute_tool", new_callable=AsyncMock, return_value="[HTTP 200]\nok"):
            with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
                events = []
                async for event in _stream_response(
                    llm_client=llm_client,
                    messages=[{"role": "user", "content": "날씨"}],
                    sources=[],
                    conversation_id=1,
                    session_id="s1",
                    ls_logger=ls_logger,
                    ls_run_id=None,
                    ls_llm_run_id=None,
                    openai_tools=[{"type": "function"}],
                    tool_map={"get_weather": fake_tool},
                ):
                    events.append(event)

        assert llm_client.chat_with_tools.call_count == MAX_TOOL_CALLS_PER_CHAT

    @pytest.mark.asyncio
    async def test_unknown_tool_sends_error_event(self):
        """알 수 없는 tool 이름은 tool_error 이벤트로 처리된다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger

        llm_client = MagicMock()
        llm_client.chat_with_tools = AsyncMock(side_effect=[
            _make_tool_call_result("unknown_tool", {}),
            TextResult(content="결과 없음"),
        ])

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        # tool_map에 "other_tool"은 있지만 LLM이 호출한 "unknown_tool"은 없음
        other_tool = MagicMock()
        other_tool.name = "other_tool"

        with patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock):
            events = []
            async for event in _stream_response(
                llm_client=llm_client,
                messages=[{"role": "user", "content": "test"}],
                sources=[],
                conversation_id=1,
                session_id="s1",
                ls_logger=ls_logger,
                ls_run_id=None,
                ls_llm_run_id=None,
                openai_tools=[{"type": "function", "function": {"name": "other_tool"}}],
                tool_map={"other_tool": other_tool},  # unknown_tool은 없음
            ):
                events.append(event)

        event_types = [json.loads(e[len("data: "):])["type"] for e in events]
        assert "tool_error" in event_types


class TestChatWithTools:
    """LLMClient.chat_with_tools 동작 단위 검증"""

    @pytest.mark.asyncio
    async def test_tool_calls_detected_when_finish_reason_is_stop(self):
        """finish_reason이 'stop'이어도 msg.tool_calls가 있으면 ToolCallResult를 반환해야 함."""
        from app.services.llm import LLMClient

        tc = MagicMock()
        tc.id = "call_abc"
        tc.function.name = "search"
        tc.function.arguments = '{"query": "test"}'

        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.content = None

        choice = MagicMock()
        choice.finish_reason = "stop"  # Ollama 등이 "stop"으로 반환하는 케이스
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

            client = LLMClient()
            result = await client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
            )

        from app.services.llm import ToolCallResult
        assert isinstance(result, ToolCallResult)
        assert result.tool_calls[0].function.name == "search"

    @pytest.mark.asyncio
    async def test_chat_with_tools_does_not_pass_tool_choice_param(self):
        """chat_with_tools가 tool_choice를 명시하지 않아 모든 Ollama 모델과 호환되어야 함."""
        from app.services.llm import LLMClient

        msg = MagicMock()
        msg.tool_calls = None
        msg.content = "직접 응답"

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            create_mock = AsyncMock(return_value=mock_response)
            mock_openai.chat.completions.create = create_mock

            client = LLMClient()
            await client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
            )

        call_kwargs = create_mock.call_args[1]
        assert "tool_choice" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_with_tools_uses_temperature_zero_by_default(self):
        """chat_with_tools는 Gemma4 호환을 위해 기본 temperature=0을 사용해야 한다."""
        from app.services.llm import LLMClient

        msg = MagicMock()
        msg.tool_calls = None
        msg.content = "응답"

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            create_mock = AsyncMock(return_value=mock_response)
            mock_openai.chat.completions.create = create_mock

            client = LLMClient()
            await client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
            )

        call_kwargs = create_mock.call_args[1]
        assert call_kwargs["temperature"] == 0.0, (
            f"chat_with_tools는 temperature=0이어야 하는데 {call_kwargs['temperature']}가 사용됨 "
            "(Gemma4 tool calling은 temperature=0 필수)"
        )

    @pytest.mark.asyncio
    async def test_temperature_zero_not_overridden_by_settings(self):
        """temperature=0.0을 명시적으로 전달하면 settings 기본값(0.7)으로 덮어쓰이지 않아야 한다."""
        from app.services.llm import LLMClient

        msg = MagicMock()
        msg.tool_calls = None
        msg.content = "응답"

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message = msg

        mock_response = MagicMock()
        mock_response.choices = [choice]

        with patch("app.services.llm.AsyncOpenAI") as mock_cls:
            mock_openai = MagicMock()
            mock_cls.return_value = mock_openai
            create_mock = AsyncMock(return_value=mock_response)
            mock_openai.chat.completions.create = create_mock

            client = LLMClient()
            # temperature=0.0은 falsy이므로 `0.0 or default`에서 default가 선택되는 버그 검증
            await client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
                temperature=0.0,
            )

        call_kwargs = create_mock.call_args[1]
        assert call_kwargs["temperature"] == 0.0, (
            f"temperature=0.0이 {call_kwargs['temperature']}로 덮어쓰임 "
            "(0.0 or default 패턴 버그)"
        )
