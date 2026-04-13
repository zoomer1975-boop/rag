"""테넌트 관리 API"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    system_prompt: str | None = None
    lang_policy: str = "auto"
    default_lang: str = "ko"
    allowed_langs: str = "ko,en,ja,zh"
    allowed_domains: str = ""
    widget_config: dict = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    system_prompt: str | None = None
    lang_policy: str | None = None
    default_lang: str | None = None
    allowed_langs: str | None = None
    allowed_domains: str | None = None
    widget_config: dict | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    api_key: str
    is_active: bool
    lang_policy: str
    default_lang: str
    allowed_langs: str
    allowed_domains: str
    widget_config: dict
    system_prompt: str | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, db: AsyncSession = Depends(get_db)):
    default_widget = {
        "primary_color": "#0066ff",
        "greeting": "안녕하세요! 무엇을 도와드릴까요?",
        "position": "bottom-right",
        "title": "챗봇",
        "placeholder": "메시지를 입력하세요...",
    }
    widget_config = {**default_widget, **body.widget_config}

    tenant = Tenant(
        name=body.name,
        api_key=Tenant.generate_api_key(),
        system_prompt=body.system_prompt,
        lang_policy=body.lang_policy,
        default_lang=body.default_lang,
        allowed_langs=body.allowed_langs,
        allowed_domains=body.allowed_domains,
        widget_config=widget_config,
    )
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int, body: TenantUpdate, db: AsyncSession = Depends(get_db)
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tenant, field, value)

    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.post("/{tenant_id}/rotate-key", response_model=TenantResponse)
async def rotate_api_key(tenant_id: int, db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    tenant.api_key = Tenant.generate_api_key()
    await db.flush()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_id: int, db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")
    await db.delete(tenant)
    await db.commit()


class DomainAdd(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)


@router.post("/{tenant_id}/domains", response_model=TenantResponse)
async def add_domain(
    tenant_id: int, body: DomainAdd, db: AsyncSession = Depends(get_db)
):
    """도메인 화이트리스트에 도메인 추가"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    domains = tenant.allowed_domain_list
    domain = body.domain.strip().lower()
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="유효하지 않은 도메인 형식입니다.")
    if domain in domains:
        return tenant  # already present — idempotent

    domains.append(domain)
    tenant.allowed_domains = ",".join(domains)
    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return tenant


@router.delete("/{tenant_id}/domains/{domain_index}", response_model=TenantResponse)
async def remove_domain(
    tenant_id: int, domain_index: int, db: AsyncSession = Depends(get_db)
):
    """도메인 화이트리스트에서 도메인 제거 (0-based index)"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="테넌트를 찾을 수 없습니다.")

    domains = tenant.allowed_domain_list
    if domain_index < 0 or domain_index >= len(domains):
        raise HTTPException(status_code=400, detail="유효하지 않은 도메인 인덱스입니다.")

    domains.pop(domain_index)
    tenant.allowed_domains = ",".join(domains)
    await db.flush()
    await db.refresh(tenant)
    await db.commit()
    return tenant
