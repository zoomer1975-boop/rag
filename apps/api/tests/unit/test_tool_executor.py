"""Tool Executor 단위 테스트"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.tool_executor import build_openai_tools, execute_tool


def _make_tool(
    name="get_weather",
    description="날씨 조회",
    http_method="GET",
    url_template="https://api.weather.com/v1/{city}/current",
    headers_encrypted=None,
    query_params_schema=None,
    body_schema=None,
    response_jmespath=None,
    timeout_seconds=10,
    is_active=True,
):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.http_method = http_method
    tool.url_template = url_template
    tool.headers_encrypted = headers_encrypted
    tool.query_params_schema = query_params_schema
    tool.body_schema = body_schema
    tool.response_jmespath = response_jmespath
    tool.timeout_seconds = timeout_seconds
    tool.is_active = is_active
    return tool


class TestBuildOpenaiTools:
    def test_basic_tool_conversion(self):
        """기본 tool이 OpenAI 형식으로 변환된다."""
        tool = _make_tool(
            query_params_schema={
                "properties": {"q": {"type": "string", "description": "검색어"}},
                "required": ["q"],
            }
        )
        result = build_openai_tools([tool])

        assert len(result) == 1
        assert result[0]["type"] == "function"
        func = result[0]["function"]
        assert func["name"] == "get_weather"
        assert "city" in func["parameters"]["properties"]  # path param
        assert "q" in func["parameters"]["properties"]
        assert "city" in func["parameters"]["required"]
        assert "q" in func["parameters"]["required"]

    def test_inactive_tool_excluded(self):
        """비활성 tool은 제외된다."""
        active = _make_tool(name="active_tool", is_active=True)
        inactive = _make_tool(name="inactive_tool", is_active=False)
        result = build_openai_tools([active, inactive])
        names = [r["function"]["name"] for r in result]
        assert "active_tool" in names
        assert "inactive_tool" not in names

    def test_tool_without_path_params(self):
        """path parameter가 없는 tool도 정상 변환된다."""
        tool = _make_tool(url_template="https://api.example.com/data")
        result = build_openai_tools([tool])
        assert result[0]["function"]["parameters"]["required"] == []

    def test_body_schema_included(self):
        """body_schema의 properties가 포함된다."""
        tool = _make_tool(
            http_method="POST",
            url_template="https://api.example.com/send",
            body_schema={
                "properties": {
                    "message": {"type": "string"},
                    "recipient": {"type": "string"},
                },
                "required": ["message"],
            },
        )
        result = build_openai_tools([tool])
        props = result[0]["function"]["parameters"]["properties"]
        assert "message" in props
        assert "recipient" in props


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_get_request_with_path_and_query(self):
        """path param과 query param이 올바르게 분리된다."""
        tool = _make_tool(
            url_template="https://api.example.com/v1/{city}/weather",
            query_params_schema={
                "properties": {"units": {"type": "string"}},
                "required": [],
            },
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"temp": 25}'

        with (
            patch("app.services.tool_executor.validate_url", new_callable=AsyncMock),
            patch("app.services.tool_executor.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await execute_tool(tool, {"city": "Seoul", "units": "metric"})

        # request 호출 인자 확인
        call_kwargs = mock_client.request.call_args
        assert "Seoul" in call_kwargs.kwargs.get("url", call_kwargs.args[1] if len(call_kwargs.args) > 1 else "")
        assert "[HTTP 200]" in result

    @pytest.mark.asyncio
    async def test_post_request_with_body(self):
        """POST 요청에서 body_schema 인자가 json body로 전송된다."""
        tool = _make_tool(
            http_method="POST",
            url_template="https://api.example.com/notify",
            body_schema={
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = b'{"ok": true}'

        with (
            patch("app.services.tool_executor.validate_url", new_callable=AsyncMock),
            patch("app.services.tool_executor.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await execute_tool(tool, {"message": "hello"})

        assert "[HTTP 201]" in result
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs.get("json") == {"message": "hello"}

    @pytest.mark.asyncio
    async def test_ssrf_error_propagated(self):
        """SSRF 오류가 그대로 전파된다."""
        from app.services.ssrf_guard import SSRFError

        tool = _make_tool(url_template="http://internal.corp/api")

        with patch("app.services.tool_executor.validate_url", new_callable=AsyncMock) as mock_validate:
            mock_validate.side_effect = SSRFError("내부 IP")
            with pytest.raises(SSRFError):
                await execute_tool(tool, {})

    @pytest.mark.asyncio
    async def test_response_truncated_at_max_bytes(self):
        """응답이 MAX_RESPONSE_BYTES를 초과하면 잘린다."""
        from app.services.tool_executor import MAX_RESPONSE_BYTES

        tool = _make_tool(url_template="https://api.example.com/big")
        large_body = b"x" * (MAX_RESPONSE_BYTES + 1000)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = large_body

        with (
            patch("app.services.tool_executor.validate_url", new_callable=AsyncMock),
            patch("app.services.tool_executor.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await execute_tool(tool, {})

        # MAX_RESPONSE_BYTES + "[HTTP 200]\n" 헤더 정도의 길이여야 함
        assert len(result) <= MAX_RESPONSE_BYTES + 20

    @pytest.mark.asyncio
    async def test_encrypted_headers_decrypted(self):
        """암호화된 헤더가 복호화되어 요청에 포함된다."""
        from app.services.encryption import encrypt

        tool = _make_tool(
            url_template="https://api.example.com/data",
            headers_encrypted=encrypt(json.dumps({"X-API-Key": "secret123"})),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        with (
            patch("app.services.tool_executor.validate_url", new_callable=AsyncMock),
            patch("app.services.tool_executor.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await execute_tool(tool, {})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs.get("headers") == {"X-API-Key": "secret123"}
