"""Redis 기반 슬라이딩 윈도우 요청 속도 제한 미들웨어

Redis 장애 시 인메모리 슬라이딩 윈도우로 자동 전환(degraded mode)합니다.
"""

import asyncio
import logging
import time
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)

# 속도 제한을 적용할 경로 prefix
_RATE_LIMITED_PREFIXES = ("/api/v1/chat", "/api/v1/ingest")

# 인메모리 폴백: api_key → 요청 타임스탬프 목록
_fallback_store: dict[str, list[float]] = defaultdict(list)
_fallback_lock = asyncio.Lock()


async def _check_fallback(api_key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """인메모리 슬라이딩 윈도우 체크.

    Returns:
        (exceeded, request_count, reset_at)
    """
    async with _fallback_lock:
        now = time.time()
        window_start = now - window
        timestamps = _fallback_store[api_key]
        # 만료된 항목 제거
        _fallback_store[api_key] = [t for t in timestamps if t > window_start]
        _fallback_store[api_key].append(now)
        count = len(_fallback_store[api_key])
    reset_at = int(now) + window
    return count > limit, count, reset_at


class RateLimitMiddleware(BaseHTTPMiddleware):
    """X-API-Key 기준 슬라이딩 윈도우 속도 제한.

    settings.rate_limit_requests / rate_limit_window 값을 사용합니다.
    Redis에 연결할 수 없으면 인메모리 폴백으로 전환합니다 (fail-closed).
    """

    def __init__(self, app, redis_url: str, limit: int, window: int) -> None:
        super().__init__(app)
        self._redis_url = redis_url
        self._limit = limit
        self._window = window
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _rate_limit_response(self, reset_at: int) -> Response:
        return Response(
            content='{"detail":"요청 한도를 초과했습니다. 잠시 후 다시 시도하세요."}',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
            headers={
                "X-RateLimit-Limit": str(self._limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
                "Retry-After": str(self._window),
            },
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not any(path.startswith(p) for p in _RATE_LIMITED_PREFIXES):
            return await call_next(request)

        api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if not api_key:
            return await call_next(request)

        try:
            redis = await self._get_redis()
            now = time.time()
            window_start = now - self._window
            redis_key = f"rl:{api_key}"

            pipe = redis.pipeline()
            pipe.zremrangebyscore(redis_key, "-inf", window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, self._window)
            results = await pipe.execute()
            request_count = results[2]

            remaining = max(0, self._limit - request_count)
            reset_at = int(now) + self._window

            if request_count > self._limit:
                return self._rate_limit_response(reset_at)

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(self._limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_at)
            return response

        except Exception as exc:
            logger.warning(
                "속도 제한 Redis 오류 — 인메모리 폴백으로 전환: %s", exc
            )
            exceeded, count, reset_at = await _check_fallback(
                api_key, self._limit, self._window
            )
            if exceeded:
                return self._rate_limit_response(reset_at)

            response = await call_next(request)
            remaining = max(0, self._limit - count)
            response.headers["X-RateLimit-Limit"] = str(self._limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_at)
            return response
