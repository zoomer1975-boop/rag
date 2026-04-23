"""add pii_config to tenants

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "pii_config",
            JSONB,
            nullable=False,
            server_default='{"enabled": false, "types": ["NAME","ADDRESS","PHONE","EMAIL","SSN","CARD","BRN"]}',
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "pii_config")
