"""관리자 인증 라우터"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.sub_admin import SubAdmin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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

    # 1. 최고관리자 체크
    if req.username == settings.admin_username and req.password == settings.admin_password:
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
            detail=f"IP 주소 {client_ip}는 허용되지 않습니다.",
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
