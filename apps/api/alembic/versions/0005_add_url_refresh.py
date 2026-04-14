"""add url refresh scheduling columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents 테이블에 URL 갱신 컬럼 추가
    op.add_column("documents", sa.Column("refresh_interval_hours", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_documents_next_refresh_at", "documents", ["next_refresh_at"])

    # tenants 테이블에 기본 갱신 주기 컬럼 추가
    op.add_column("tenants", sa.Column("default_url_refresh_hours", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_index("ix_documents_next_refresh_at", table_name="documents")
    op.drop_column("documents", "next_refresh_at")
    op.drop_column("documents", "last_refreshed_at")
    op.drop_column("documents", "refresh_interval_hours")
    op.drop_column("tenants", "default_url_refresh_hours")
