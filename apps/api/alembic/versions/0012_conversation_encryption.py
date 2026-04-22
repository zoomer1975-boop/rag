"""Add conversation encryption columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tenants: DEK 저장 컬럼 (MEK로 감싼 per-tenant Data Encryption Key)
    op.add_column(
        "tenants",
        sa.Column("encrypted_dek", sa.Text(), nullable=True),
    )

    # messages: 암호화된 본문 컬럼 추가, 기존 content는 nullable로 변경
    op.add_column(
        "messages",
        sa.Column("content_enc", sa.Text(), nullable=True),
    )
    op.alter_column(
        "messages",
        "content",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    # content를 다시 NOT NULL로 복원 (데이터 손실 주의)
    op.alter_column(
        "messages",
        "content",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("messages", "content_enc")
    op.drop_column("tenants", "encrypted_dek")
