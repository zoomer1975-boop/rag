"""Add clarification support columns

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "clarification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("clarification_config", JSONB(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "message_type",
            sa.String(32),
            nullable=False,
            server_default="text",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("clarification_meta", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "clarification_meta")
    op.drop_column("messages", "message_type")
    op.drop_column("tenants", "clarification_config")
    op.drop_column("tenants", "clarification_enabled")
