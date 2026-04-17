"""Tool calling 실제 API 통합 테스트

https://api.dkit.kr/t.php — GET 파라미터 없이 장난감 재고 JSON 반환
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.tool_executor import build_openai_tools, execute_tool


def _toy_tool():
    """https://api.dkit.kr/t.php 를 가리키는 TenantApiTool 목."""
    tool = MagicMock()
    tool.name = "get_toy_inventory"
    tool.description = "장난감 재고 목록을 조회합니다. 파라미터 없이 호출하세요."
    tool.http_method = "GET"
    tool.url_template = "https://api.dkit.kr/t.php"
    tool.headers_encrypted = None
    tool.query_params_schema = None
    tool.body_schema = None
    tool.response_jmespath = None
    tool.timeout_seconds = 10
    tool.is_active = True
    return tool


# ── execute_tool 직접 호출 (실제 HTTP) ────────────────────────────────────────

class TestExecuteToolRealHttp:
    """execute_tool이 실제 외부 API를 호출한다."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_get_returns_toy_list(self):
        """실제 GET 요청이 성공하고 장난감 목록 JSON을 반환해야 한다."""
        tool = _toy_tool()
        result = await execute_tool(tool, {})

        assert "[HTTP 200]" in result
        parsed = json.loads(result.replace("[HTTP 200]\n", ""))
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_response_contains_expected_fields(self):
        """응답 JSON 각 항목에 장난감명, 수량, 판매처, 설명 필드가 있어야 한다."""
        tool = _toy_tool()
        result = await execute_tool(tool, {})

        body = result[result.index("\n") + 1:]
        items = json.loads(body)
        first = items[0]
        assert "장난감명" in first
        assert "수량" in first
        assert "판매처" in first
        assert "설명" in first

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jmespath_extracts_toy_names(self):
        """response_jmespath로 장난감명 배열만 추출할 수 있다."""
        tool = _toy_tool()
        tool.response_jmespath = '[*]."장난감명"'  # 한글 필드는 JMESPath 따옴표 필요
        result = await execute_tool(tool, {})

        body = result[result.index("\n") + 1:]
        names = json.loads(body)
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        assert len(names) > 0


# ── _stream_response 통합 흐름 (LLM mock + 실제 HTTP tool) ────────────────────

class TestStreamResponseWithRealTool:
    """_stream_response에서 LLM이 get_toy_inventory 도구를 호출하면
    실제 HTTP 요청이 발생하고 결과가 최종 응답에 반영된다."""

    def _make_tool_call_result(self, tool_name: str, arguments: dict, tc_id: str = "tc_toy_001"):
        from app.services.llm import ToolCallResult

        tc = MagicMock()
        tc.id = tc_id
        tc.function.name = tool_name
        tc.function.arguments = json.dumps(arguments)

        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tc_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps(arguments)},
            }],
        }
        return ToolCallResult(tool_calls=[tc], assistant_message=assistant_msg)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_llm_calls_toy_tool_and_gets_real_data(self):
        """LLM이 get_toy_inventory 도구를 요청 → 실제 HTTP 호출 → 결과 포함 최종 응답."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger
        from app.services.llm import TextResult

        toy_tool = _toy_tool()
        openai_tools = build_openai_tools([toy_tool])

        llm_client = MagicMock()
        # 1차: tool 호출 요청
        tool_call_result = self._make_tool_call_result("get_toy_inventory", {})
        # 2차: 실제 데이터를 받은 후 텍스트 응답
        final_text = TextResult(content="현재 재고에 삐뽀삐뽀 구급차 5개, 말랑말랑 슬라임 12개 등이 있습니다.")
        llm_client.chat_with_tools = AsyncMock(side_effect=[tool_call_result, final_text])

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        events = []
        with patch_save_message():
            async for event in _stream_response(
                llm_client=llm_client,
                messages=[{"role": "user", "content": "장난감 재고 알려줘"}],
                sources=[],
                conversation_id=1,
                session_id="test-session",
                ls_logger=ls_logger,
                ls_run_id=None,
                ls_llm_run_id=None,
                openai_tools=openai_tools,
                tool_map={"get_toy_inventory": toy_tool},
            ):
                events.append(event)

        event_types = [json.loads(e[len("data: "):])["type"] for e in events]

        # tool_call 이벤트 확인
        assert "tool_call" in event_types, "tool_call SSE 이벤트가 없음"

        # tool_result 이벤트 확인 + 실제 데이터 포함 여부
        tool_result_events = [
            json.loads(e[len("data: "):])
            for e in events
            if '"tool_result"' in e
        ]
        assert len(tool_result_events) == 1
        preview = tool_result_events[0]["preview"]
        assert "장난감명" in preview or "HTTP 200" in preview, (
            f"실제 API 응답이 preview에 없음: {preview!r}"
        )

        # 최종 텍스트 응답 확인
        assert "token" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_tool_result_messages_sent_to_llm(self):
        """execute_tool 결과가 tool role 메시지로 LLM에 전달되어야 한다."""
        from app.routers.chat import _stream_response
        from app.services.langsmith_logger import LangSmithLogger
        from app.services.llm import TextResult

        toy_tool = _toy_tool()
        openai_tools = build_openai_tools([toy_tool])

        captured_messages = []

        async def _capture_chat_with_tools(messages, tools, **kwargs):
            captured_messages.append(list(messages))
            if len(captured_messages) == 1:
                return self._make_tool_call_result("get_toy_inventory", {})
            return TextResult(content="재고 확인 완료")

        llm_client = MagicMock()
        llm_client.chat_with_tools = _capture_chat_with_tools

        ls_logger = MagicMock(spec=LangSmithLogger)
        ls_logger.log_llm_end = AsyncMock()
        ls_logger.end_trace = AsyncMock()

        with patch_save_message():
            async for _ in _stream_response(
                llm_client=llm_client,
                messages=[{"role": "user", "content": "재고 알려줘"}],
                sources=[],
                conversation_id=1,
                session_id="test-session-2",
                ls_logger=ls_logger,
                ls_run_id=None,
                ls_llm_run_id=None,
                openai_tools=openai_tools,
                tool_map={"get_toy_inventory": toy_tool},
            ):
                pass

        # 2번째 LLM 호출 메시지에 tool role 메시지가 포함되어야 함
        assert len(captured_messages) == 2
        second_call_messages = captured_messages[1]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "장난감명" in tool_messages[0]["content"] or "HTTP 200" in tool_messages[0]["content"]


# ── helpers ───────────────────────────────────────────────────────────────────

def patch_save_message():
    """_save_assistant_message를 no-op AsyncMock으로 교체하는 컨텍스트 매니저."""
    from unittest.mock import patch
    return patch("app.routers.chat._save_assistant_message", new_callable=AsyncMock)
