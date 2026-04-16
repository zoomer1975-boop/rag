"""테넌트별 Web API Tool 설정 모델"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

MAX_TOOLS_PER_TENANT = 10


class TenantApiTool(Base):
    __tablename__ = "tenant_api_tools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_api_tool_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # OpenAI function calling에서 사용하는 tool 식별자 (영문 소문자/숫자/언더스코어)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    # HTTP 설정
    http_method: Mapped[str] = mapped_column(String(10), nullable=False, default="GET")  # GET/POST/PUT/PATCH/DELETE
    url_template: Mapped[str] = mapped_column(String(2000), nullable=False)

    # 암호화된 요청 헤더 JSON (API key 등 민감 정보 포함 가능)
    headers_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM이 채울 파라미터 스키마 (JSON Schema 형식)
    # query_params_schema: GET 쿼리 파라미터, body_schema: POST/PUT 바디
    query_params_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    body_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 응답에서 필요한 부분만 추출하는 JMESPath 표현식 (옵션)
    response_jmespath: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 요청 타임아웃 (초, 최대 30)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="api_tools")  # noqa: F821
