"""system health 헬퍼 함수 단위 테스트

테스트 대상 (apps/api/app/routers/admin.py):
  - _check_postgresql
  - _check_redis
  - _check_http_models
  - _check_safeguard
  - _check_ner
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.admin import (
    ServiceStatus,
    _check_http_models,
    _check_ner,
    _check_postgresql,
    _check_redis,
    _check_safeguard,
)


# ─── _check_ner (순수 동기, mock 불필요) ────────────────────────────────────


class TestCheckNer:
    """_check_ner: NER 모델 설정 여부만 검사하는 순수 함수"""

    def test_empty_string_returns_down(self):
        # Arrange
        model_name = ""
        # Act
        result = _check_ner(model_name)
        # Assert
        assert result.status == "down"
        assert result.message == "모델 미설정"

    def test_none_equivalent_empty_returns_down(self):
        # 빈 문자열과 동일 경로 — 추가 방어적 케이스
        result = _check_ner("")
        assert result.status == "down"

    def test_nonempty_model_name_returns_ok(self):
        # Arrange
        model_name = "ko-pii-ner-v1"
        # Act
        result = _check_ner(model_name)
        # Assert
        assert result.status == "ok"
        assert result.message is None  # 모델명 노출 금지 (H-2)

    def test_whitespace_only_treated_as_falsy(self):
        # "  " — Python에서 bool("  ") is True → 모델명으로 인식
        # 이 동작이 의도적임을 문서화
        result = _check_ner("   ")
        assert result.status == "ok"

    def test_returns_service_status_instance(self):
        result = _check_ner("some-model")
        assert isinstance(result, ServiceStatus)


# ─── _check_postgresql ──────────────────────────────────────────────────────


class TestCheckPostgresql:
    """_check_postgresql: AsyncSession.execute 결과에 따른 상태 반환"""

    @pytest.mark.asyncio
    async def test_success_returns_ok(self):
        # Arrange
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        # Act
        result = await _check_postgresql(mock_db)
        # Assert
        assert result.status == "ok"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_success_has_no_error_message(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        result = await _check_postgresql(mock_db)
        assert result.message is None

    @pytest.mark.asyncio
    async def test_exception_returns_down(self):
        # Arrange
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))
        # Act
        result = await _check_postgresql(mock_db)
        # Assert
        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_exception_does_not_expose_raw_error(self):
        # C-2: raw 예외 메시지가 클라이언트에 노출되어서는 안 된다
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("SSL SYSCALL error: internal host=db.internal"))
        result = await _check_postgresql(mock_db)
        assert result.message is not None
        assert "SSL SYSCALL error" not in result.message
        assert "db.internal" not in result.message

    @pytest.mark.asyncio
    async def test_exception_has_generic_message(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))
        result = await _check_postgresql(mock_db)
        assert result.status == "down"
        assert result.message == "연결 실패"

    @pytest.mark.asyncio
    async def test_exception_still_includes_latency(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("timeout"))
        result = await _check_postgresql(mock_db)
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_service_status_instance(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        result = await _check_postgresql(mock_db)
        assert isinstance(result, ServiceStatus)


# ─── _check_redis ───────────────────────────────────────────────────────────


class TestCheckRedis:
    """_check_redis: aioredis.from_url → ping 결과에 따른 상태 반환"""

    @pytest.mark.asyncio
    async def test_ping_success_returns_ok(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert result.status == "ok"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_ping_success_no_message(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert result.message is None

    @pytest.mark.asyncio
    async def test_ping_timeout_returns_down(self):
        mock_client = AsyncMock()
        # asyncio.wait_for 가 TimeoutError를 raise하게 시뮬레이션
        mock_client.ping = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_connection_error_returns_down(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert result.status == "down"
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_exception_includes_latency(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("auth error"))
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_aclose_called_on_success(self):
        """aclose()는 성공 시에도 반드시 호출되어야 한다"""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            await _check_redis("redis://localhost:6379")

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aclose_called_on_exception(self):
        """aclose()는 예외 시에도 finally에서 호출되어야 한다"""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("boom"))
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            await _check_redis("redis://any")

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_service_status_instance(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://localhost:6379")

        assert isinstance(result, ServiceStatus)

    @pytest.mark.asyncio
    async def test_exception_does_not_expose_raw_error(self):
        # C-2: Redis URL 등 내부 정보가 노출되어서는 안 된다
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("WRONGPASS invalid password redis://user:secret@db.internal:6379"))
        mock_client.aclose = AsyncMock()

        with patch("app.routers.admin.aioredis.from_url", return_value=mock_client):
            result = await _check_redis("redis://user:secret@db.internal:6379")

        assert result.status == "down"
        assert "secret" not in (result.message or "")
        assert "db.internal" not in (result.message or "")
        assert result.message == "연결 실패"


# ─── _check_http_models ─────────────────────────────────────────────────────


def _make_httpx_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestCheckHttpModels:
    """_check_http_models: httpx GET /models 응답 코드에 따른 상태 반환"""

    @pytest.mark.asyncio
    async def test_http_200_returns_ok(self):
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "ok"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_url_has_models_suffix(self):
        """base_url에 /models가 append되는지 확인"""
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            await _check_http_models("http://localhost:11434/v1", "sk-test", "llm")

        called_url = mock_client.get.call_args[0][0]
        assert called_url == "http://localhost:11434/v1/models"

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped_before_appending(self):
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            await _check_http_models("http://localhost:11434/v1/", "key", "emb")

        called_url = mock_client.get.call_args[0][0]
        assert called_url == "http://localhost:11434/v1/models"

    @pytest.mark.asyncio
    async def test_http_4xx_returns_degraded(self):
        mock_resp = _make_httpx_response(401)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "bad-key", "llm")

        assert result.status == "degraded"
        assert "401" in (result.message or "")

    @pytest.mark.asyncio
    async def test_http_5xx_returns_degraded(self):
        mock_resp = _make_httpx_response(503)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "degraded"
        assert "503" in (result.message or "")

    @pytest.mark.asyncio
    async def test_http_399_boundary_returns_ok(self):
        """399는 < 400 이므로 ok"""
        mock_resp = _make_httpx_response(399)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_http_400_boundary_returns_degraded(self):
        """400은 >= 400 이므로 degraded"""
        mock_resp = _make_httpx_response(400)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "degraded"

    @pytest.mark.asyncio
    async def test_network_error_returns_down(self):
        import httpx as _httpx

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(
            side_effect=_httpx.ConnectError("connection refused")
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "down"
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_timeout_returns_down(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=_httpx.TimeoutException("timed out")
        )
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_exception_includes_latency(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_service_status_instance(self):
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://localhost:11434/v1", "key", "llm")

        assert isinstance(result, ServiceStatus)

    @pytest.mark.asyncio
    async def test_exception_does_not_expose_internal_url(self):
        # C-2: 내부 URL이나 raw 예외 정보가 클라이언트에 노출되어서는 안 된다
        import httpx as _httpx

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(
            side_effect=_httpx.ConnectError("Failed to connect to http://internal-llm.corp:11434/v1")
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_http_models("http://internal-llm.corp:11434/v1", "key", "llm")

        assert result.status == "down"
        assert "internal-llm.corp" not in (result.message or "")
        assert result.message == "연결 실패"


# ─── _check_safeguard ───────────────────────────────────────────────────────


class TestCheckSafeguard:
    """_check_safeguard: disabled 분기 / HTTP 성공·실패·예외"""

    @pytest.mark.asyncio
    async def test_disabled_returns_down_with_flag(self):
        # Arrange: enabled=False → 즉시 반환, HTTP 호출 없음
        result = await _check_safeguard("http://safeguard:8080/v1", enabled=False)
        assert result.status == "down"
        assert result.enabled is False
        assert result.message == "disabled"

    @pytest.mark.asyncio
    async def test_disabled_does_not_call_http(self):
        with patch("app.routers.admin.httpx.AsyncClient") as mock_cls:
            await _check_safeguard("http://safeguard:8080/v1", enabled=False)
        mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_url_strips_v1_suffix(self):
        """base_url의 /v1을 제거하고 /health를 붙여야 한다"""
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        called_url = mock_client.get.call_args[0][0]
        assert called_url == "http://safeguard:8080/health"

    @pytest.mark.asyncio
    async def test_health_url_port_ending_in_1_not_corrupted(self):
        """포트 끝자리가 1인 URL에서 rstrip('/v1')이 포트 숫자를 잘라내는 버그 재현.
        예: http://safeguard:8001/v1 → rstrip 오용 시 http://safeguard:800/health"""
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            await _check_safeguard("http://safeguard:8001/v1", enabled=True)

        called_url = mock_client.get.call_args[0][0]
        assert called_url == "http://safeguard:8001/health"

    @pytest.mark.asyncio
    async def test_health_url_trailing_slash_after_v1(self):
        """base_url이 /v1/로 끝나도 올바른 /health URL을 생성해야 한다"""
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            await _check_safeguard("http://safeguard:8001/v1/", enabled=True)

        called_url = mock_client.get.call_args[0][0]
        assert called_url == "http://safeguard:8001/health"

    @pytest.mark.asyncio
    async def test_http_200_returns_ok(self):
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert result.status == "ok"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_http_4xx_returns_degraded(self):
        mock_resp = _make_httpx_response(404)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert result.status == "degraded"
        assert "404" in (result.message or "")

    @pytest.mark.asyncio
    async def test_network_exception_returns_down(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("refused"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert result.status == "down"
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_exception_includes_latency(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_service_status_instance(self):
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert isinstance(result, ServiceStatus)

    @pytest.mark.asyncio
    async def test_exception_does_not_expose_raw_error(self):
        # C-2: 내부 호스트 등 raw 예외 정보가 노출되어서는 안 된다
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=_httpx.ConnectError("Connection refused: http://safeguard.internal:8080/health")
        )
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard.internal:8080/v1", enabled=True)

        assert result.status == "down"
        assert "safeguard.internal" not in (result.message or "")
        assert result.message == "연결 실패"

    @pytest.mark.asyncio
    async def test_enabled_true_is_reflected_in_response(self):
        """enabled=True 경로에서 반환된 ServiceStatus.enabled는 True여야 한다"""
        mock_resp = _make_httpx_response(200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.admin.httpx.AsyncClient", return_value=mock_cm):
            result = await _check_safeguard("http://safeguard:8080/v1", enabled=True)

        assert result.enabled is True
