import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 위젯 설정
    widget_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "primary_color": "#0066ff",
            "greeting": "안녕하세요! 무엇을 도와드릴까요?",
            "position": "bottom-right",
            "title": "챗봇",
            "placeholder": "메시지를 입력하세요...",
        },
    )

    # 다국어 정책
    lang_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto"
    )  # auto | fixed | whitelist
    default_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="ko")
    allowed_langs: Mapped[str] = mapped_column(
        String(200), nullable=False, default="ko,en,ja,zh"
    )

    # 도메인 화이트리스트 (쉼표 구분, 빈 문자열 = 전체 허용)
    allowed_domains: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    # 시스템 프롬프트 (테넌트별 커스텀)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # URL 자동 갱신 기본 주기 (시간, 0 = 비활성)
    default_url_refresh_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")  # noqa: F821
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")  # noqa: F821

    @staticmethod
    def generate_api_key() -> str:
        return f"tenant_{secrets.token_urlsafe(32)}"

    @property
    def allowed_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.allowed_langs.split(",")]

    @property
    def allowed_domain_list(self) -> list[str]:
        if not self.allowed_domains.strip():
            return []
        return [d.strip() for d in self.allowed_domains.split(",") if d.strip()]
