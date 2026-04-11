"""add allowed_domains to tenants

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("allowed_domains", sa.String(2000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("tenants", "allowed_domains")
