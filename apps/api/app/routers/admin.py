"""관리자(최고관리자) 전용 라우터 - 부관리자 관리"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.middleware.auth import verify_admin
from app.models.sub_admin import SubAdmin, sub_admin_tenants

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ─── System Health ────────────────────────────────────────────────────────────


class ServiceStatus(BaseModel):
    status: Literal["ok", "degraded", "down"]
    latency_ms: float | None = None
    message: str | None = None
    enabled: bool = True


class SystemHealthResponse(BaseModel):
    postgresql: ServiceStatus
    redis: ServiceStatus
    llm: ServiceStatus
    embedding: ServiceStatus
    safeguard: ServiceStatus
    ner: ServiceStatus
    checked_at: str


async def _check_postgresql(db: AsyncSession) -> ServiceStatus:
    t0 = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        return ServiceStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception:
        logger.exception("PostgreSQL health check failed")
        return ServiceStatus(status="down", latency_ms=round((time.monotonic() - t0) * 1000, 1), message="연결 실패")


async def _check_redis(redis_url: str) -> ServiceStatus:
    t0 = time.monotonic()
    client = aioredis.from_url(redis_url, socket_connect_timeout=3)
    try:
        await asyncio.wait_for(client.ping(), timeout=3)
        return ServiceStatus(status="ok", latency_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception:
        logger.exception("Redis health check failed")
        return ServiceStatus(status="down", latency_ms=round((time.monotonic() - t0) * 1000, 1), message="연결 실패")
    finally:
        await client.aclose()


async def _check_http_models(base_url: str, api_key: str, label: str) -> ServiceStatus:
    t0 = time.monotonic()
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        latency = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code < 400:
            return ServiceStatus(status="ok", latency_ms=latency)
        return ServiceStatus(status="degraded", latency_ms=latency, message=f"HTTP {resp.status_code}")
    except Exception:
        logger.exception("HTTP model health check failed: %s", label)
        return ServiceStatus(status="down", latency_ms=round((time.monotonic() - t0) * 1000, 1), message="연결 실패")


async def _check_safeguard(base_url: str, enabled: bool) -> ServiceStatus:
    if not enabled:
        return ServiceStatus(status="down", enabled=False, message="disabled")
    # rstrip은 개별 문자를 제거하므로 suffix 제거에 사용하면 안 됨
    base = base_url.rstrip("/").removesuffix("/v1")
    health_url = base + "/health"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(health_url)
        latency = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code < 400:
            return ServiceStatus(status="ok", latency_ms=latency)
        return ServiceStatus(status="degraded", latency_ms=latency, message=f"HTTP {resp.status_code}")
    except Exception:
        logger.exception("Safeguard health check failed")
        return ServiceStatus(status="down", latency_ms=round((time.monotonic() - t0) * 1000, 1), message="연결 실패")


def _check_ner(model_name: str) -> ServiceStatus:
    if not model_name:
        return ServiceStatus(status="down", message="모델 미설정")
    return ServiceStatus(status="ok")


@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
) -> SystemHealthResponse:
    """인프라 서비스 상태 일괄 조회 (최고관리자 전용)"""
    settings = get_settings()

    pg, rd, llm, emb, sg = await asyncio.gather(
        _check_postgresql(db),
        _check_redis(settings.redis_url),
        _check_http_models(settings.llm_base_url, settings.llm_api_key, "llm"),
        _check_http_models(settings.embedding_base_url, settings.embedding_api_key, "embedding"),
        _check_safeguard(settings.safeguard_base_url, settings.safeguard_enabled),
    )
    ner = _check_ner(settings.pii_ner_model)

    return SystemHealthResponse(
        postgresql=pg,
        redis=rd,
        llm=llm,
        embedding=emb,
        safeguard=sg,
        ner=ner,
        checked_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


# ─── Request/Response Models ──────────────────────────────────────────────────


class SubAdminCreate(BaseModel):
    """부관리자 생성"""

    name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=72)
    allowed_ips: str = ""
    tenant_ids: list[int] = Field(default_factory=list)


class SubAdminUpdate(BaseModel):
    """부관리자 수정"""

    name: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=72)
    is_active: bool | None = None
    allowed_ips: str | None = None
    tenant_ids: list[int] | None = None


class SubAdminResponse(BaseModel):
    """부관리자 응답"""

    id: int
    name: str
    username: str
    is_active: bool
    allowed_ips: str
    created_at: datetime
    tenant_ids: list[int]

    model_config = {"from_attributes": True}


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/sub-admins", response_model=list[SubAdminResponse])
async def list_sub_admins(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """부관리자 목록 조회 (최고관리자만)"""
    result = await db.execute(select(SubAdmin).order_by(SubAdmin.created_at.desc()))
    sub_admins = result.scalars().all()

    response = []
    for sub_admin in sub_admins:
        # tenant_ids 조회
        tenant_ids_result = await db.execute(
            select(sub_admin_tenants.c.tenant_id).where(
                sub_admin_tenants.c.sub_admin_id == sub_admin.id
            )
        )
        tenant_ids = [row[0] for row in tenant_ids_result.fetchall()]

        response.append(
            SubAdminResponse(
                **{k: v for k, v in sub_admin.__dict__.items() if not k.startswith("_")},
                tenant_ids=tenant_ids,
            )
        )

    return response


@router.post("/sub-admins", response_model=SubAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_sub_admin(
    body: SubAdminCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """부관리자 생성 (최고관리자만)"""
    # username 중복 체크
    existing = await db.execute(
        select(SubAdmin).where(SubAdmin.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 존재하는 아이디입니다.",
        )

    # 부관리자 생성
    sub_admin = SubAdmin(
        name=body.name,
        username=body.username,
        password_hash=SubAdmin.hash_password(body.password),
        allowed_ips=body.allowed_ips,
    )
    db.add(sub_admin)
    await db.flush()
    await db.refresh(sub_admin)

    # tenant 할당
    if body.tenant_ids:
        for tenant_id in body.tenant_ids:
            await db.execute(
                sub_admin_tenants.insert().values(
                    sub_admin_id=sub_admin.id, tenant_id=tenant_id
                )
            )

    await db.commit()

    return SubAdminResponse(
        **{k: v for k, v in sub_admin.__dict__.items() if not k.startswith("_")},
        tenant_ids=body.tenant_ids,
    )


@router.patch("/sub-admins/{sub_admin_id}", response_model=SubAdminResponse)
async def update_sub_admin(
    sub_admin_id: int,
    body: SubAdminUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """부관리자 수정 (최고관리자만)"""
    sub_admin = await db.get(SubAdmin, sub_admin_id)
    if not sub_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부관리자를 찾을 수 없습니다.",
        )

    # 필드 업데이트
    if body.name is not None:
        sub_admin.name = body.name
    if body.password is not None:
        sub_admin.password_hash = SubAdmin.hash_password(body.password)
    if body.is_active is not None:
        sub_admin.is_active = body.is_active
    if body.allowed_ips is not None:
        sub_admin.allowed_ips = body.allowed_ips

    await db.flush()
    await db.refresh(sub_admin)

    # tenant_ids 업데이트
    if body.tenant_ids is not None:
        # 기존 할당 제거
        await db.execute(
            delete(sub_admin_tenants).where(
                sub_admin_tenants.c.sub_admin_id == sub_admin.id
            )
        )
        # 새로운 할당 추가
        for tenant_id in body.tenant_ids:
            await db.execute(
                sub_admin_tenants.insert().values(
                    sub_admin_id=sub_admin.id, tenant_id=tenant_id
                )
            )

    await db.commit()

    # tenant_ids 조회
    tenant_ids_result = await db.execute(
        select(sub_admin_tenants.c.tenant_id).where(
            sub_admin_tenants.c.sub_admin_id == sub_admin.id
        )
    )
    tenant_ids = [row[0] for row in tenant_ids_result.fetchall()]

    return SubAdminResponse(
        **{k: v for k, v in sub_admin.__dict__.items() if not k.startswith("_")},
        tenant_ids=tenant_ids,
    )


@router.delete("/sub-admins/{sub_admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sub_admin(
    sub_admin_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """부관리자 삭제 (최고관리자만)"""
    sub_admin = await db.get(SubAdmin, sub_admin_id)
    if not sub_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부관리자를 찾을 수 없습니다.",
        )

    await db.delete(sub_admin)
    await db.commit()
