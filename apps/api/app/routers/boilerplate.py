"""테넌트별 상용문구(boilerplate) 패턴 관리 API"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import verify_admin
from app.models.boilerplate_pattern import BoilerplatePattern
from app.services.boilerplate import (
    _MAX_PATTERNS_PER_TENANT,
    apply,
    load_patterns,
    validate_pattern,
)

router = APIRouter(
    prefix="/api/v1/tenants/{tenant_id}/boilerplate",
    tags=["boilerplate"],
    dependencies=[Depends(verify_admin)],
)


# ─── Schemas ──────────────────────────────────────────────────────────────────


class PatternCreate(BaseModel):
    pattern_type: str = Field(..., pattern="^(literal|regex)$")
    pattern: str = Field(..., min_length=1, max_length=10000)
    description: str | None = Field(None, max_length=255)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("pattern")
    @classmethod
    def strip_pattern(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("패턴은 빈 문자열일 수 없습니다.")
        return v


class PatternUpdate(BaseModel):
    pattern_type: str | None = Field(None, pattern="^(literal|regex)$")
    pattern: str | None = Field(None, min_length=1, max_length=10000)
    description: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    sort_order: int | None = None


class PatternResponse(BaseModel):
    id: int
    tenant_id: int
    pattern_type: str
    pattern: str
    description: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreviewRequest(BaseModel):
    sample_text: str = Field(..., min_length=1, max_length=50_000)


class PreviewResponse(BaseModel):
    original: str
    applied: str
    removed_count: int


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _get_pattern_or_404(db: AsyncSession, tenant_id: int, pattern_id: int) -> BoilerplatePattern:
    row = await db.get(BoilerplatePattern, pattern_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="패턴을 찾을 수 없습니다.")
    return row


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[PatternResponse])
async def list_patterns(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BoilerplatePattern)
        .where(BoilerplatePattern.tenant_id == tenant_id)
        .order_by(BoilerplatePattern.sort_order, BoilerplatePattern.id)
    )
    return result.scalars().all()


@router.post("", response_model=PatternResponse, status_code=status.HTTP_201_CREATED)
async def create_pattern(
    tenant_id: int,
    body: PatternCreate,
    db: AsyncSession = Depends(get_db),
):
    # 최대 개수 체크
    count_result = await db.execute(
        select(func.count()).where(BoilerplatePattern.tenant_id == tenant_id)
    )
    if count_result.scalar() >= _MAX_PATTERNS_PER_TENANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"테넌트당 최대 {_MAX_PATTERNS_PER_TENANT}개까지 등록할 수 있습니다.",
        )

    # 패턴 유효성 검사
    err = validate_pattern(body.pattern_type, body.pattern)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    row = BoilerplatePattern(
        tenant_id=tenant_id,
        pattern_type=body.pattern_type,
        pattern=body.pattern,
        description=body.description,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="동일한 패턴이 이미 등록되어 있습니다.",
        )
    await db.refresh(row)
    return row


@router.patch("/{pattern_id}", response_model=PatternResponse)
async def update_pattern(
    tenant_id: int,
    pattern_id: int,
    body: PatternUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await _get_pattern_or_404(db, tenant_id, pattern_id)

    new_type = body.pattern_type if body.pattern_type is not None else row.pattern_type
    new_pattern = body.pattern if body.pattern is not None else row.pattern

    if body.pattern_type is not None or body.pattern is not None:
        err = validate_pattern(new_type, new_pattern)
        if err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if body.pattern_type is not None:
        row.pattern_type = body.pattern_type
    if body.pattern is not None:
        row.pattern = body.pattern
    if body.description is not None:
        row.description = body.description
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.sort_order is not None:
        row.sort_order = body.sort_order

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="동일한 패턴이 이미 등록되어 있습니다.",
        )
    await db.refresh(row)
    return row


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pattern(
    tenant_id: int,
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = await _get_pattern_or_404(db, tenant_id, pattern_id)
    await db.delete(row)
    await db.commit()


@router.post("/preview", response_model=PreviewResponse)
async def preview_patterns(
    tenant_id: int,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """현재 저장된 활성 패턴을 샘플 텍스트에 적용한 결과를 반환합니다."""
    patterns = await load_patterns(db, tenant_id)
    applied = apply(body.sample_text, patterns)
    removed_count = sum(
        1 for p in patterns
        if (p.kind == "literal" and p.value in body.sample_text)
        or (p.kind == "regex" and p.value.search(body.sample_text))
    )
    return PreviewResponse(
        original=body.sample_text,
        applied=applied,
        removed_count=removed_count,
    )
