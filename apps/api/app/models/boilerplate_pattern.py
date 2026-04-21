from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BoilerplatePattern(Base):
    __tablename__ = "tenant_boilerplate_patterns"
    __table_args__ = (
        CheckConstraint("pattern_type IN ('literal', 'regex')", name="ck_boilerplate_pattern_type"),
        UniqueConstraint("tenant_id", "pattern_type", "pattern", name="uq_boilerplate_tenant_type_pattern"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'literal' | 'regex'
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="boilerplate_patterns")  # noqa: F821
