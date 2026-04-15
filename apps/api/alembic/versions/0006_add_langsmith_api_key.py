"""add langsmith_api_key to tenants

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("langsmith_api_key", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "langsmith_api_key")
