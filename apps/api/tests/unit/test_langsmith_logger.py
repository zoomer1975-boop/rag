"""LangSmith 로거 서비스 단위 테스트"""

import asyncio
import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.langsmith_logger import LangSmithLogger, create_logger


class TestLangSmithLoggerInit:
    def test_no_key_creates_noop_logger(self):
        logger = LangSmithLogger(api_key=None)
        assert not logger.is_enabled

    def test_empty_key_creates_noop_logger(self):
        logger = LangSmithLogger(api_key="")
        assert not logger.is_enabled

    def test_valid_key_creates_enabled_logger(self):
        logger = LangSmithLogger(api_key="ls__test_key_abc123")
        assert logger.is_enabled

    def test_create_logger_factory_no_key(self):
        logger = create_logger(api_key=None)
        assert isinstance(logger, LangSmithLogger)
        assert not logger.is_enabled

    def test_create_logger_factory_with_key(self):
        logger = create_logger(api_key="ls__test_key_abc123")
        assert isinstance(logger, LangSmithLogger)
        assert logger.is_enabled


class TestLangSmithLoggerAsync:
    """LangSmith 메서드가 async-safe한지 검증 (event loop 블로킹 방지)."""

    def test_start_trace_is_coroutine(self):
        """start_trace가 async def여야 함 — 동기 호출 시 event loop 블로킹 방지."""
        assert inspect.iscoroutinefunction(LangSmithLogger.start_trace)

    def test_end_trace_is_coroutine(self):
        assert inspect.iscoroutinefunction(LangSmithLogger.end_trace)

    def test_log_retrieval_is_coroutine(self):
        assert inspect.iscoroutinefunction(LangSmithLogger.log_retrieval)

    def test_log_llm_start_is_coroutine(self):
        assert inspect.iscoroutinefunction(LangSmithLogger.log_llm_start)

    def test_log_llm_end_is_coroutine(self):
        assert inspect.iscoroutinefunction(LangSmithLogger.log_llm_end)

    @pytest.mark.asyncio
    async def test_start_trace_does_not_block_on_slow_sdk(self):
        """SDK가 느려도 5초 이내에 타임아웃 처리되어야 함."""
        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        def _slow_create_run(**kwargs):
            time.sleep(10)  # SDK 블로킹 시뮬레이션

        mock_client.create_run.side_effect = _slow_create_run

        with patch("app.services.langsmith_logger.Client", mock_client_cls):
            logger = LangSmithLogger(api_key="ls__test_key", project_name="proj")
            start = asyncio.get_event_loop().time()
            result = await logger.start_trace(run_name="test", inputs={})
            elapsed = asyncio.get_event_loop().time() - start

        assert result is None  # 타임아웃 → None 반환
        assert elapsed < 6.0  # 10초 sleep인데 6초 내에 완료

    @pytest.mark.asyncio
    async def test_noop_logger_start_trace_returns_none(self):
        """키 없는 no-op 로거의 async start_trace는 None을 반환한다."""
        logger = LangSmithLogger(api_key=None)
        result = await logger.start_trace(run_name="test", inputs={})
        assert result is None


class TestLangSmithLoggerNoop:
    """키 없을 때 no-op 동작 확인 — 예외 없이 조용히 무시."""

    def setup_method(self):
        self.logger = LangSmithLogger(api_key=None)

    @pytest.mark.asyncio
    async def test_start_trace_returns_none(self):
        result = await self.logger.start_trace(run_name="test", inputs={"query": "hello"})
        assert result is None

    @pytest.mark.asyncio
    async def test_end_trace_with_none_run_id_is_safe(self):
        await self.logger.end_trace(run_id=None, outputs={"response": "hi"})

    @pytest.mark.asyncio
    async def test_end_trace_with_error_is_safe(self):
        await self.logger.end_trace(run_id=None, error="some error")

    @pytest.mark.asyncio
    async def test_log_retrieval_is_safe(self):
        await self.logger.log_retrieval(
            parent_run_id=None,
            query="hello",
            chunks=[{"content": "chunk1", "score": 0.9}],
        )


class TestLangSmithLoggerEnabled:
    """키 있을 때 LangSmith SDK 호출 확인."""

    def setup_method(self):
        self.mock_client_cls = MagicMock()
        self.mock_client = MagicMock()
        self.mock_client_cls.return_value = self.mock_client

        self.patcher = patch("app.services.langsmith_logger.Client", self.mock_client_cls)
        self.patcher.start()

        self.logger = LangSmithLogger(api_key="ls__test_key_abc123")

    def teardown_method(self):
        self.patcher.stop()

    def test_client_initialized_with_api_key(self):
        self.mock_client_cls.assert_called_once_with(api_key="ls__test_key_abc123")

    @pytest.mark.asyncio
    async def test_start_trace_creates_run(self):
        run_id = await self.logger.start_trace(
            run_name="rag_chat",
            inputs={"query": "안녕하세요"},
        )
        assert run_id is not None
        assert len(run_id) == 36  # UUID 형식
        self.mock_client.create_run.assert_called_once()
        call_kwargs = self.mock_client.create_run.call_args[1]
        assert call_kwargs["name"] == "rag_chat"
        assert call_kwargs["inputs"] == {"query": "안녕하세요"}
        assert call_kwargs["id"] == run_id

    @pytest.mark.asyncio
    async def test_end_trace_updates_run(self):
        await self.logger.end_trace(run_id="run-uuid-123", outputs={"response": "hello"})
        self.mock_client.update_run.assert_called_once()
        call_kwargs = self.mock_client.update_run.call_args[1]
        assert call_kwargs["run_id"] == "run-uuid-123"
        assert call_kwargs["outputs"] == {"response": "hello"}

    @pytest.mark.asyncio
    async def test_end_trace_with_error_marks_error(self):
        await self.logger.end_trace(run_id="run-uuid-123", error="LLM timeout")
        call_kwargs = self.mock_client.update_run.call_args[1]
        assert call_kwargs["error"] == "LLM timeout"

    @pytest.mark.asyncio
    async def test_end_trace_none_run_id_skips_update(self):
        """run_id가 None이면 update_run을 호출하지 않아야 함."""
        await self.logger.end_trace(run_id=None, outputs={})
        self.mock_client.update_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_retrieval_creates_child_run(self):
        await self.logger.log_retrieval(
            parent_run_id="parent-run-id",
            query="검색 쿼리",
            chunks=[{"content": "문서 내용", "score": 0.85}],
        )
        self.mock_client.create_run.assert_called_once()
        call_kwargs = self.mock_client.create_run.call_args[1]
        assert call_kwargs["parent_run_id"] == "parent-run-id"

    @pytest.mark.asyncio
    async def test_log_retrieval_none_parent_skips_call(self):
        """parent_run_id가 None이면 retrieval 로깅 건너뜀."""
        await self.logger.log_retrieval(parent_run_id=None, query="쿼리", chunks=[])
        self.mock_client.create_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_llm_start_creates_llm_child_run(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant.\n\nContext: ..."},
            {"role": "user", "content": "안녕하세요"},
        ]
        llm_run_id = await self.logger.log_llm_start(
            parent_run_id="parent-run-id",
            messages=messages,
        )
        assert llm_run_id is not None
        assert len(llm_run_id) == 36
        self.mock_client.create_run.assert_called_once()
        call_kwargs = self.mock_client.create_run.call_args[1]
        assert call_kwargs["run_type"] == "llm"
        assert call_kwargs["parent_run_id"] == "parent-run-id"
        assert call_kwargs["inputs"]["messages"] == messages

    @pytest.mark.asyncio
    async def test_log_llm_start_none_parent_skips_call(self):
        result = await self.logger.log_llm_start(parent_run_id=None, messages=[])
        assert result is None
        self.mock_client.create_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_llm_end_updates_run_with_response(self):
        await self.logger.log_llm_end(run_id="llm-run-id", response="안녕하세요!")
        self.mock_client.update_run.assert_called_once()
        call_kwargs = self.mock_client.update_run.call_args[1]
        assert call_kwargs["run_id"] == "llm-run-id"
        assert call_kwargs["outputs"]["response"] == "안녕하세요!"
        assert "end_time" in call_kwargs

    @pytest.mark.asyncio
    async def test_log_llm_end_none_run_id_is_noop(self):
        await self.logger.log_llm_end(run_id=None, response="hi")
        self.mock_client.update_run.assert_not_called()


class TestLangSmithLoggerSdkFailure:
    """LangSmith SDK 오류 발생 시 주요 기능에 영향을 주지 않음 확인."""

    def setup_method(self):
        self.mock_client_cls = MagicMock()
        self.mock_client = MagicMock()
        self.mock_client_cls.return_value = self.mock_client
        self.mock_client.create_run.side_effect = Exception("LangSmith API error")

        self.patcher = patch("app.services.langsmith_logger.Client", self.mock_client_cls)
        self.patcher.start()

        self.logger = LangSmithLogger(api_key="ls__test_key_abc123")

    def teardown_method(self):
        self.patcher.stop()

    @pytest.mark.asyncio
    async def test_start_trace_swallows_sdk_exception(self):
        """SDK 오류 시 None을 반환하고 예외를 전파하지 않음."""
        result = await self.logger.start_trace(run_name="rag_chat", inputs={})
        assert result is None
