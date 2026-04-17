"""LangSmith 로거 서비스

테넌트별 LangSmith API 키가 있을 때 RAG/LLM 호출을 LangSmith에 기록합니다.
키가 없으면 모든 메서드가 no-op으로 동작하여 주요 기능에 영향을 주지 않습니다.

SDK 호출은 asyncio.to_thread + 5초 타임아웃으로 래핑되어
느린 네트워크나 LangSmith 서버 문제로 인한 event loop 블로킹을 방지합니다.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_LANGSMITH_TIMEOUT = 5.0  # SDK 호출 최대 대기 시간(초)

try:
    from langsmith import Client
except ImportError:
    Client = None  # type: ignore[assignment,misc]


async def _call_sdk(func, **kwargs) -> bool:
    """동기 SDK 함수를 thread pool에서 실행하고 타임아웃을 적용한다.

    Returns:
        True if successful, False on timeout or error.
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(func, **kwargs),
            timeout=_LANGSMITH_TIMEOUT,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("LangSmith SDK 호출 타임아웃 (%.1fs 초과): %s", _LANGSMITH_TIMEOUT, func.__name__)
        return False
    except Exception as exc:
        logger.warning("LangSmith SDK 호출 실패: %s", exc)
        return False


class LangSmithLogger:
    """테넌트별 LangSmith 로거.

    api_key가 없거나 langsmith 패키지가 없으면 no-op으로 동작합니다.
    모든 메서드는 async이며 SDK 호출은 thread pool + 타임아웃으로 보호됩니다.
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

    async def start_trace(
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
            ok = await _call_sdk(self._client.create_run, **kwargs)
            return run_id if ok else None
        except Exception as exc:
            logger.warning("LangSmith start_trace 실패: %s", exc)
            return None

    async def end_trace(
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
            await _call_sdk(self._client.update_run, **kwargs)
        except Exception as exc:
            logger.warning("LangSmith end_trace 실패: %s", exc)

    async def log_retrieval(
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
            await _call_sdk(
                self._client.create_run,
                id=retrieval_run_id,
                name="vector_retrieval",
                run_type="retriever",
                inputs={"query": query},
                parent_run_id=parent_run_id,
                start_time=datetime.now(timezone.utc),
            )
            await _call_sdk(
                self._client.update_run,
                run_id=retrieval_run_id,
                outputs={"documents": chunks},
                end_time=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("LangSmith log_retrieval 실패: %s", exc)

    async def log_llm_start(
        self,
        parent_run_id: str | None,
        messages: list[dict[str, Any]],
    ) -> str | None:
        """LLM 호출을 llm child run으로 기록하고 run_id를 반환합니다."""
        if not self.is_enabled or parent_run_id is None:
            return None
        try:
            llm_run_id = str(uuid.uuid4())
            ok = await _call_sdk(
                self._client.create_run,
                id=llm_run_id,
                name="llm_call",
                run_type="llm",
                inputs={"messages": messages},
                parent_run_id=parent_run_id,
                start_time=datetime.now(timezone.utc),
            )
            return llm_run_id if ok else None
        except Exception as exc:
            logger.warning("LangSmith log_llm_start 실패: %s", exc)
            return None

    async def log_llm_end(
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
            await _call_sdk(self._client.update_run, **kwargs)
        except Exception as exc:
            logger.warning("LangSmith log_llm_end 실패: %s", exc)


def create_logger(api_key: str | None, project_name: str | None = None) -> LangSmithLogger:
    """테넌트 api_key로부터 LangSmithLogger 인스턴스를 생성합니다."""
    return LangSmithLogger(api_key=api_key, project_name=project_name)
