"""LangSmith 로거 서비스

테넌트별 LangSmith API 키가 있을 때 RAG/LLM 호출을 LangSmith에 기록합니다.
키가 없으면 모든 메서드가 no-op으로 동작하여 주요 기능에 영향을 주지 않습니다.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger(__name__)

try:
    from langsmith import Client
except ImportError:
    Client = None  # type: ignore[assignment,misc]


class LangSmithLogger:
    """테넌트별 LangSmith 로거.

    api_key가 없거나 langsmith 패키지가 없으면 no-op으로 동작합니다.
    SDK 오류가 발생해도 예외를 전파하지 않아 주요 기능에 영향을 주지 않습니다.
    """

    def __init__(self, api_key: str | None, project_name: str | None = None) -> None:
        self._client: Any = None
        self._project_name = project_name
        if api_key and Client is not None:
            try:
                self._client = Client(api_key=api_key)
            except Exception:
                logger.warning("LangSmith 클라이언트 초기화 실패 — 로깅이 비활성화됩니다.")

    @property
    def is_enabled(self) -> bool:
        return self._client is not None

    def start_trace(
        self,
        run_name: str,
        inputs: dict[str, Any],
        run_type: str = "chain",
        parent_run_id: str | None = None,
    ) -> str | None:
        """새 실행(run)을 LangSmith에 등록하고 run_id를 반환합니다."""
        if not self.is_enabled:
            return None
        try:
            run_id = str(uuid.uuid4())
            kwargs: dict[str, Any] = {
                "id": run_id,
                "name": run_name,
                "run_type": run_type,
                "inputs": inputs,
                "start_time": datetime.now(timezone.utc),
            }
            if parent_run_id is not None:
                kwargs["parent_run_id"] = parent_run_id
            elif self._project_name is not None:
                kwargs["project_name"] = self._project_name
            self._client.create_run(**kwargs)
            return run_id
        except Exception as exc:
            logger.warning("LangSmith start_trace 실패: %s", exc)
            return None

    def end_trace(
        self,
        run_id: str | None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """실행(run)을 종료하고 출력 또는 오류를 기록합니다."""
        if not self.is_enabled or run_id is None:
            return
        try:
            kwargs: dict[str, Any] = {
                "run_id": run_id,
                "end_time": datetime.now(timezone.utc),
            }
            if outputs is not None:
                kwargs["outputs"] = outputs
            if error is not None:
                kwargs["error"] = error
            self._client.update_run(**kwargs)
        except Exception as exc:
            logger.warning("LangSmith end_trace 실패: %s", exc)

    def log_retrieval(
        self,
        parent_run_id: str | None,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """벡터 검색 결과를 retriever child run으로 기록합니다."""
        if not self.is_enabled or parent_run_id is None:
            return
        try:
            retrieval_run_id = str(uuid.uuid4())
            self._client.create_run(
                id=retrieval_run_id,
                name="vector_retrieval",
                run_type="retriever",
                inputs={"query": query},
                parent_run_id=parent_run_id,
                start_time=datetime.now(timezone.utc),
            )
            self._client.update_run(
                run_id=retrieval_run_id,
                outputs={"documents": chunks},
                end_time=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("LangSmith log_retrieval 실패: %s", exc)

    def log_llm_start(
        self,
        parent_run_id: str | None,
        messages: list[dict[str, Any]],
    ) -> str | None:
        """LLM 호출을 llm child run으로 기록하고 run_id를 반환합니다.

        messages 배열에는 system prompt, 대화 히스토리, 사용자 메시지가 포함되어
        LangSmith에서 전체 프롬프트를 확인할 수 있습니다.
        """
        if not self.is_enabled or parent_run_id is None:
            return None
        try:
            llm_run_id = str(uuid.uuid4())
            self._client.create_run(
                id=llm_run_id,
                name="llm_call",
                run_type="llm",
                inputs={"messages": messages},
                parent_run_id=parent_run_id,
                start_time=datetime.now(timezone.utc),
            )
            return llm_run_id
        except Exception as exc:
            logger.warning("LangSmith log_llm_start 실패: %s", exc)
            return None

    def log_llm_end(
        self,
        run_id: str | None,
        response: str,
        error: str | None = None,
    ) -> None:
        """LLM 응답을 기록하고 llm child run을 종료합니다."""
        if not self.is_enabled or run_id is None:
            return
        try:
            kwargs: dict[str, Any] = {
                "run_id": run_id,
                "end_time": datetime.now(timezone.utc),
                "outputs": {"response": response},
            }
            if error is not None:
                kwargs["error"] = error
            self._client.update_run(**kwargs)
        except Exception as exc:
            logger.warning("LangSmith log_llm_end 실패: %s", exc)

    @contextmanager
    def trace(
        self,
        run_name: str,
        inputs: dict[str, Any],
        run_type: str = "chain",
    ) -> Generator[str | None, None, None]:
        """컨텍스트 매니저로 run 시작/종료를 자동으로 처리합니다.

        Usage:
            with logger.trace("rag_chat", inputs={"query": q}) as run_id:
                # run_id를 child run에 parent_run_id로 전달
        """
        run_id = self.start_trace(run_name=run_name, inputs=inputs, run_type=run_type)
        try:
            yield run_id
            self.end_trace(run_id=run_id, outputs={"status": "ok"})
        except Exception as exc:
            self.end_trace(run_id=run_id, error=str(exc))
            raise


def create_logger(api_key: str | None, project_name: str | None = None) -> LangSmithLogger:
    """테넌트 api_key로부터 LangSmithLogger 인스턴스를 생성합니다."""
    return LangSmithLogger(api_key=api_key, project_name=project_name)
