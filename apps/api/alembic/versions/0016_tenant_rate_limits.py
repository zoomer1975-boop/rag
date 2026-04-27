"""tenant rate limits

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27

"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("rate_limit_requests", sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("rate_limit_window", sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("max_documents", sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("max_api_tools", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "max_api_tools")
    op.drop_column("tenants", "max_documents")
    op.drop_column("tenants", "rate_limit_window")
    op.drop_column("tenants", "rate_limit_requests")
