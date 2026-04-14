"""부관리자 모델"""

import ipaddress
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# 비밀번호 해싱 컨텍스트 (argon2, bcrypt fallback)
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# 중간 테이블: sub_admin_tenants
sub_admin_tenants = Table(
    "sub_admin_tenants",
    Base.metadata,
    Column("sub_admin_id", Integer, ForeignKey("sub_admins.id", ondelete="CASCADE"), primary_key=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
)


class SubAdmin(Base):
    """부관리자 모델"""

    __tablename__ = "sub_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_ips: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


    @staticmethod
    def hash_password(plain_password: str) -> str:
        """평문 비밀번호를 bcrypt로 해싱합니다."""
        return pwd_context.hash(plain_password)

    def verify_password(self, plain_password: str) -> bool:
        """평문 비밀번호가 저장된 해시와 일치하는지 검증합니다."""
        return pwd_context.verify(plain_password, self.password_hash)

    def is_ip_allowed(self, request_ip: str) -> bool:
        """요청한 IP가 허용된 IP 목록에 있는지 검증합니다.

        Args:
            request_ip: 요청 IP 주소 (또는 IPv6)

        Returns:
            True if IP is allowed, False otherwise.
            빈 allowed_ips면 모든 IP 허용.
        """
        # 빈 allowed_ips면 모든 IP 허용
        if not self.allowed_ips.strip():
            return True

        try:
            request_ip_obj = ipaddress.ip_address(request_ip)
        except ValueError:
            # 유효하지 않은 IP 형식
            return False

        # 허용된 IP/CIDR 목록을 파싱
        allowed_entries = [entry.strip() for entry in self.allowed_ips.split(",") if entry.strip()]

        for entry in allowed_entries:
            try:
                # CIDR 범위 확인
                if "/" in entry:
                    allowed_network = ipaddress.ip_network(entry, strict=False)
                    if request_ip_obj in allowed_network:
                        return True
                else:
                    # 정확한 IP 확인
                    allowed_ip = ipaddress.ip_address(entry)
                    if request_ip_obj == allowed_ip:
                        return True
            except ValueError:
                # 유효하지 않은 IP/CIDR 형식은 무시
                continue

        return False
