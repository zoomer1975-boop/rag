"""API Key 인증 미들웨어"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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


async def verify_admin(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> None:
    """X-Admin-Token 헤더로 관리자 인증을 검증합니다."""
    settings = get_settings()
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 API 토큰이 서버에 설정되지 않았습니다.",
        )
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 관리자 토큰입니다.",
        )
