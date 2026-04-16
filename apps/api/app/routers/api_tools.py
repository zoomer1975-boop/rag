"""테넌트별 Web API Tool CRUD — 관리자 전용"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import verify_admin
from app.models.tenant_api_tool import MAX_TOOLS_PER_TENANT, TenantApiTool
from app.services.encryption import decrypt, encrypt, mask_header_values

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/api-tools", tags=["api-tools"])

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_MAX_TIMEOUT = 30


class ApiToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=500)
    http_method: str = Field("GET", max_length=10)
    url_template: str = Field(..., min_length=1, max_length=2000)
    headers: dict[str, str] | None = None  # 저장 시 암호화됨
    query_params_schema: dict | None = None
    body_schema: dict | None = None
    response_jmespath: str | None = Field(None, max_length=500)
    timeout_seconds: int = Field(10, ge=1, le=_MAX_TIMEOUT)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name은 소문자 영문으로 시작하고 소문자/숫자/언더스코어만 허용됩니다.")
        return v

    @field_validator("http_method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _ALLOWED_METHODS:
            raise ValueError(f"http_method는 {_ALLOWED_METHODS} 중 하나여야 합니다.")
        return upper

    @field_validator("url_template")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url_template은 http:// 또는 https://로 시작해야 합니다.")
        return v


class ApiToolUpdate(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=500)
    http_method: str | None = Field(None, max_length=10)
    url_template: str | None = Field(None, min_length=1, max_length=2000)
    headers: dict[str, str] | None = None
    query_params_schema: dict | None = None
    body_schema: dict | None = None
    response_jmespath: str | None = Field(None, max_length=500)
    timeout_seconds: int | None = Field(None, ge=1, le=_MAX_TIMEOUT)
    is_active: bool | None = None

    @field_validator("http_method")
    @classmethod
    def validate_method(cls, v: str | None) -> str | None:
        if v is None:
            return v
        upper = v.upper()
        if upper not in _ALLOWED_METHODS:
            raise ValueError(f"http_method는 {_ALLOWED_METHODS} 중 하나여야 합니다.")
        return upper

    @field_validator("url_template")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url_template은 http:// 또는 https://로 시작해야 합니다.")
        return v


class ApiToolResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str
    http_method: str
    url_template: str
    headers_masked: dict[str, str] | None  # 마스킹된 헤더 값
    query_params_schema: dict | None
    body_schema: dict | None
    response_jmespath: str | None
    timeout_seconds: int
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_tool(cls, tool: TenantApiTool) -> "ApiToolResponse":
        masked: dict[str, str] | None = None
        if tool.headers_encrypted:
            try:
                raw = json.loads(decrypt(tool.headers_encrypted))
                masked = mask_header_values(raw)
            except Exception:
                masked = None
        return cls(
            id=tool.id,
            tenant_id=tool.tenant_id,
            name=tool.name,
            description=tool.description,
            http_method=tool.http_method,
            url_template=tool.url_template,
            headers_masked=masked,
            query_params_schema=tool.query_params_schema,
            body_schema=tool.body_schema,
            response_jmespath=tool.response_jmespath,
            timeout_seconds=tool.timeout_seconds,
            is_active=tool.is_active,
        )


async def _get_tool_or_404(tool_id: int, tenant_id: int, db: AsyncSession) -> TenantApiTool:
    result = await db.execute(
        select(TenantApiTool).where(
            TenantApiTool.id == tool_id,
            TenantApiTool.tenant_id == tenant_id,
        )
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="API Tool을 찾을 수 없습니다.")
    return tool


@router.get("/", response_model=list[ApiToolResponse])
async def list_api_tools(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """테넌트의 API Tool 목록 조회"""
    result = await db.execute(
        select(TenantApiTool)
        .where(TenantApiTool.tenant_id == tenant_id)
        .order_by(TenantApiTool.created_at.asc())
    )
    return [ApiToolResponse.from_tool(t) for t in result.scalars().all()]


@router.post("/", response_model=ApiToolResponse, status_code=status.HTTP_201_CREATED)
async def create_api_tool(
    tenant_id: int,
    body: ApiToolCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """API Tool 등록"""
    # 개수 제한 확인
    count_result = await db.execute(
        select(TenantApiTool).where(TenantApiTool.tenant_id == tenant_id)
    )
    existing = count_result.scalars().all()
    if len(existing) >= MAX_TOOLS_PER_TENANT:
        raise HTTPException(
            status_code=400,
            detail=f"API Tool은 테넌트당 최대 {MAX_TOOLS_PER_TENANT}개까지 등록할 수 있습니다.",
        )

    # 이름 중복 확인
    name_result = await db.execute(
        select(TenantApiTool).where(
            TenantApiTool.tenant_id == tenant_id,
            TenantApiTool.name == body.name,
        )
    )
    if name_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"'{body.name}' 이름의 API Tool이 이미 존재합니다.")

    headers_encrypted = None
    if body.headers:
        headers_encrypted = encrypt(json.dumps(body.headers))

    tool = TenantApiTool(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        http_method=body.http_method,
        url_template=body.url_template,
        headers_encrypted=headers_encrypted,
        query_params_schema=body.query_params_schema,
        body_schema=body.body_schema,
        response_jmespath=body.response_jmespath,
        timeout_seconds=body.timeout_seconds,
    )
    db.add(tool)
    await db.flush()
    await db.refresh(tool)
    await db.commit()
    return ApiToolResponse.from_tool(tool)


@router.patch("/{tool_id}", response_model=ApiToolResponse)
async def update_api_tool(
    tenant_id: int,
    tool_id: int,
    body: ApiToolUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """API Tool 수정"""
    tool = await _get_tool_or_404(tool_id, tenant_id, db)

    update_data = body.model_dump(exclude_none=True)

    # headers는 별도 처리 (암호화)
    if "headers" in update_data:
        headers = update_data.pop("headers")
        tool.headers_encrypted = encrypt(json.dumps(headers)) if headers else None

    for field, value in update_data.items():
        setattr(tool, field, value)

    await db.flush()
    await db.refresh(tool)
    await db.commit()
    return ApiToolResponse.from_tool(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_tool(
    tenant_id: int,
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """API Tool 삭제"""
    tool = await _get_tool_or_404(tool_id, tenant_id, db)
    await db.delete(tool)
    await db.commit()
