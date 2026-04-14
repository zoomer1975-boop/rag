"""관리자 인증 미들웨어"""

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.sub_admin import SubAdmin


class AdminAuth:
    """관리자 인증 정보"""

    def __init__(
        self,
        is_superadmin: bool,
        sub_admin_id: int | None = None,
        tenant_ids: list[int] | None = None,
    ):
        self.is_superadmin = is_superadmin
        self.sub_admin_id = sub_admin_id
        self.tenant_ids = tenant_ids or []

    def has_tenant_access(self, tenant_id: int) -> bool:
        """특정 테넌트에 접근 권한이 있는지 확인"""
        if self.is_superadmin:
            return True
        return tenant_id in self.tenant_ids


# Note: X-Admin-Token 헤더 검증 로직은 Next.js 세션 기반으로 구현
# 지금은 placeholder만 구현
async def get_admin_auth(request: Request) -> AdminAuth:
    """관리자 인증 정보 조회

    Note: 추후 X-Admin-Token 헤더 기반으로 구현될 예정
    현재는 placeholder
    """
    # 추후 구현: X-Admin-Token 헤더에서 인증 정보 파싱
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="관리자 인증이 필요합니다.",
    )
