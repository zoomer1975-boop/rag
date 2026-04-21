"""Redis 기반 슬라이딩 윈도우 요청 속도 제한 미들웨어"""

import logging
import time

import redis.asyncio as aioredis
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)

# 속도 제한을 적용할 경로 prefix
_RATE_LIMITED_PREFIXES = ("/api/v1/chat", "/api/v1/ingest")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """X-API-Key 기준 슬라이딩 윈도우 속도 제한.

    settings.rate_limit_requests / rate_limit_window 값을 사용합니다.
    Redis에 연결할 수 없으면 요청을 허용(fail-open)합니다.
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

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(self._limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_at)
            return response

        except Exception as exc:
            logger.warning("속도 제한 Redis 오류 (fail-open): %s", exc)
            return await call_next(request)
