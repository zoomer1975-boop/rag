"""add sub_admins tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sub_admins table
    op.create_table(
        "sub_admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allowed_ips", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_sub_admins_username", "sub_admins", ["username"])

    # Create sub_admin_tenants association table
    op.create_table(
        "sub_admin_tenants",
        sa.Column(
            "sub_admin_id",
            sa.Integer(),
            sa.ForeignKey("sub_admins.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_sub_admin_tenants_tenant_id",
        "sub_admin_tenants",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("sub_admin_tenants")
    op.drop_table("sub_admins")
