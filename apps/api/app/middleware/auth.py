"""API Key 인증 미들웨어"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.tenant import Tenant


async def get_tenant(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """X-API-Key 헤더로 테넌트를 인증합니다."""
    result = await db.execute(
        select(Tenant).where(Tenant.api_key == x_api_key, Tenant.is_active == True)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 비활성화된 API 키입니다.",
        )
    return tenant
