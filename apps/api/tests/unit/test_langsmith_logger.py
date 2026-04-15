"""LangSmith 로거 서비스 단위 테스트 (TDD - RED 단계)"""

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


class TestLangSmithLoggerNoop:
    """키 없을 때 no-op 동작 확인 — 예외 없이 조용히 무시."""

    def setup_method(self):
        self.logger = LangSmithLogger(api_key=None)

    def test_start_trace_returns_none(self):
        result = self.logger.start_trace(run_name="test", inputs={"query": "hello"})
        assert result is None

    def test_end_trace_with_none_run_id_is_safe(self):
        # run_id=None이어도 예외 없어야 함
        self.logger.end_trace(run_id=None, outputs={"response": "hi"})

    def test_end_trace_with_error_is_safe(self):
        self.logger.end_trace(run_id=None, error="some error")

    def test_log_retrieval_is_safe(self):
        self.logger.log_retrieval(
            parent_run_id=None,
            query="hello",
            chunks=[{"content": "chunk1", "score": 0.9}],
        )

    def test_context_manager_noop(self):
        """컨텍스트 매니저로 사용 시 no-op."""
        with self.logger.trace("test_op", inputs={"q": "hello"}) as run_id:
            assert run_id is None


class TestLangSmithLoggerEnabled:
    """키 있을 때 LangSmith SDK 호출 확인."""

    def setup_method(self):
        # langsmith 패키지를 mock으로 교체
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

    def test_start_trace_creates_run(self):
        mock_run = MagicMock()
        mock_run.id = "run-uuid-123"
        self.mock_client.create_run.return_value = mock_run

        run_id = self.logger.start_trace(
            run_name="rag_chat",
            inputs={"query": "안녕하세요"},
        )
        assert run_id == "run-uuid-123"
        self.mock_client.create_run.assert_called_once()
        call_kwargs = self.mock_client.create_run.call_args[1]
        assert call_kwargs["name"] == "rag_chat"
        assert call_kwargs["inputs"] == {"query": "안녕하세요"}

    def test_end_trace_updates_run(self):
        self.logger.end_trace(run_id="run-uuid-123", outputs={"response": "hello"})
        self.mock_client.update_run.assert_called_once()
        call_kwargs = self.mock_client.update_run.call_args[1]
        assert call_kwargs["run_id"] == "run-uuid-123"
        assert call_kwargs["outputs"] == {"response": "hello"}

    def test_end_trace_with_error_marks_error(self):
        self.logger.end_trace(run_id="run-uuid-123", error="LLM timeout")
        call_kwargs = self.mock_client.update_run.call_args[1]
        assert call_kwargs["error"] == "LLM timeout"

    def test_end_trace_none_run_id_skips_update(self):
        """run_id가 None이면 update_run을 호출하지 않아야 함."""
        self.logger.end_trace(run_id=None, outputs={})
        self.mock_client.update_run.assert_not_called()

    def test_log_retrieval_creates_child_run(self):
        self.logger.log_retrieval(
            parent_run_id="parent-run-id",
            query="검색 쿼리",
            chunks=[{"content": "문서 내용", "score": 0.85}],
        )
        self.mock_client.create_run.assert_called_once()
        call_kwargs = self.mock_client.create_run.call_args[1]
        assert call_kwargs["parent_run_id"] == "parent-run-id"

    def test_log_retrieval_none_parent_skips_call(self):
        """parent_run_id가 None이면 retrieval 로깅 건너뜀."""
        self.logger.log_retrieval(
            parent_run_id=None,
            query="쿼리",
            chunks=[],
        )
        self.mock_client.create_run.assert_not_called()

    def test_context_manager_creates_and_ends_run(self):
        mock_run = MagicMock()
        mock_run.id = "ctx-run-id"
        self.mock_client.create_run.return_value = mock_run

        with self.logger.trace("test_op", inputs={"q": "hello"}) as run_id:
            assert run_id == "ctx-run-id"

        self.mock_client.create_run.assert_called_once()
        self.mock_client.update_run.assert_called_once()

    def test_context_manager_ends_run_on_exception(self):
        mock_run = MagicMock()
        mock_run.id = "ctx-run-id"
        self.mock_client.create_run.return_value = mock_run

        with pytest.raises(ValueError):
            with self.logger.trace("test_op", inputs={}) as run_id:
                raise ValueError("test error")

        call_kwargs = self.mock_client.update_run.call_args[1]
        assert "error" in call_kwargs


class TestLangSmithLoggerSdkFailure:
    """LangSmith SDK 오류 발생 시 주요 기능에 영향을 주지 않음 확인."""

    def setup_method(self):
        self.mock_client_cls = MagicMock()
        self.mock_client = MagicMock()
        self.mock_client_cls.return_value = self.mock_client
        # create_run이 예외를 던지도록 설정
        self.mock_client.create_run.side_effect = Exception("LangSmith API error")

        self.patcher = patch("app.services.langsmith_logger.Client", self.mock_client_cls)
        self.patcher.start()

        self.logger = LangSmithLogger(api_key="ls__test_key_abc123")

    def teardown_method(self):
        self.patcher.stop()

    def test_start_trace_swallows_sdk_exception(self):
        """SDK 오류 시 None을 반환하고 예외를 전파하지 않음."""
        result = self.logger.start_trace(run_name="rag_chat", inputs={})
        assert result is None

    def test_context_manager_swallows_sdk_exception(self):
        """컨텍스트 매니저 내 SDK 오류가 전파되지 않음."""
        with self.logger.trace("test_op", inputs={}) as run_id:
            assert run_id is None  # 오류 발생해도 None 반환
