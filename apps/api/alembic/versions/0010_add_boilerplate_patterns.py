"""add tenant_boilerplate_patterns table

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_boilerplate_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern_type", sa.String(10), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pattern_type IN ('literal', 'regex')",
            name="ck_boilerplate_pattern_type",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "pattern_type",
            "pattern",
            name="uq_boilerplate_tenant_type_pattern",
        ),
    )
    op.create_index(
        "ix_boilerplate_tenant_active",
        "tenant_boilerplate_patterns",
        ["tenant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_boilerplate_tenant_active", table_name="tenant_boilerplate_patterns")
    op.drop_table("tenant_boilerplate_patterns")
