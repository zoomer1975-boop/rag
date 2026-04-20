"""관리자 인증 라우터"""

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.sub_admin import SubAdmin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_LOGIN_RATE_LIMIT = 10   # 최대 시도 횟수
_LOGIN_RATE_WINDOW = 60  # 초


async def _check_login_rate_limit(client_ip: str) -> None:
    """Redis를 이용한 로그인 시도 속도 제한 (IP당 60초에 최대 10회)."""
    settings = get_settings()
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        key = f"login_attempts:{client_ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, _LOGIN_RATE_WINDOW)
        await r.aclose()
        if count > _LOGIN_RATE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="너무 많은 로그인 시도입니다. 잠시 후 다시 시도하세요.",
                headers={"Retry-After": str(_LOGIN_RATE_WINDOW)},
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("로그인 속도 제한 Redis 오류 — 제한 없이 진행합니다.")


class LoginRequest(BaseModel):
    """로그인 요청"""

    username: str
    password: str


class LoginResponse(BaseModel):
    """로그인 응답"""

    ok: bool
    is_superadmin: bool
    sub_admin_id: int | None = None
    tenant_ids: list[int] | None = None


_REQUIRED_TABLES: list[tuple[str, list[str]]] = [
    (
        "tenant_boilerplate_patterns",
        [
            """
            CREATE TABLE IF NOT EXISTS tenant_boilerplate_patterns (
                id          SERIAL PRIMARY KEY,
                tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                pattern_type VARCHAR(10) NOT NULL CHECK (pattern_type IN ('literal', 'regex')),
                pattern     TEXT NOT NULL,
                description VARCHAR(255),
                is_active   BOOLEAN NOT NULL DEFAULT true,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_boilerplate_tenant_type_pattern UNIQUE (tenant_id, pattern_type, pattern)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_boilerplate_tenant_active
                ON tenant_boilerplate_patterns (tenant_id, is_active)
            """,
        ],
    ),
]


async def _ensure_tables(db: AsyncSession) -> None:
    """최고관리자 로그인 시 누락된 테이블을 자동으로 생성합니다."""
    for table_name, ddl_statements in _REQUIRED_TABLES:
        result = await db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :table"
            ),
            {"table": table_name},
        )
        if result.scalar() is None:
            logger.info("자동 테이블 생성: %s", table_name)
            for ddl in ddl_statements:
                await db.execute(text(ddl))
            await db.commit()


def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출"""
    # X-Forwarded-For (프록시 뒤)
    if "x-forwarded-for" in request.headers:
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    # X-Real-IP (프록시)
    if "x-real-ip" in request.headers:
        return request.headers["x-real-ip"]
    # 직접 연결
    return request.client.host if request.client else "0.0.0.0"


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """관리자 로그인 엔드포인트"""
    settings = get_settings()
    client_ip = _get_client_ip(request)

    await _check_login_rate_limit(client_ip)

    # 1. 최고관리자 체크
    if req.username == settings.admin_username and req.password == settings.admin_password:
        await _ensure_tables(db)
        return LoginResponse(ok=True, is_superadmin=True)

    # 2. 부관리자 체크
    result = await db.execute(
        select(SubAdmin).where(
            SubAdmin.username == req.username,
            SubAdmin.is_active == True,  # noqa: E712
        )
    )
    sub_admin = result.scalar_one_or_none()

    if not sub_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    # 비밀번호 검증
    if not sub_admin.verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    # IP 검증
    if not sub_admin.is_ip_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 IP 주소에서는 접근이 허용되지 않습니다.",
        )

    # tenant_ids 조회 (association table 통해)
    # SQLAlchemy ORM 관계를 통해 tenants 조회
    # Note: 현재는 많은-대-많은 관계가 설정되지 않았으므로
    # 직접 쿼리로 조회
    from sqlalchemy import and_

    from app.models.sub_admin import sub_admin_tenants

    tenant_ids_result = await db.execute(
        select(sub_admin_tenants.c.tenant_id).where(
            sub_admin_tenants.c.sub_admin_id == sub_admin.id
        )
    )
    tenant_ids = [row[0] for row in tenant_ids_result.fetchall()]

    return LoginResponse(
        ok=True,
        is_superadmin=False,
        sub_admin_id=sub_admin.id,
        tenant_ids=tenant_ids,
    )
