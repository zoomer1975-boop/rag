from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base

settings = get_settings()


class Relationship(Base):
    """GraphRAG 엔티티 관계 — LLM이 추출한 서술 + high-level 키워드."""

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimension), nullable=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    source_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="relationships")  # noqa: F821
    source_entity: Mapped["Entity"] = relationship(  # noqa: F821
        "Entity", foreign_keys=[source_entity_id], back_populates="outgoing_relationships"
    )
    target_entity: Mapped["Entity"] = relationship(  # noqa: F821
        "Entity", foreign_keys=[target_entity_id], back_populates="incoming_relationships"
    )

    __table_args__ = (
        Index("ix_relationships_tenant_source", "tenant_id", "source_entity_id"),
        Index("ix_relationships_tenant_target", "tenant_id", "target_entity_id"),
        Index(
            "ix_relationships_description_embedding",
            "description_embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"description_embedding": "vector_cosine_ops"},
        ),
    )
