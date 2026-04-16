"""add tenant_api_tools table for web API tool calling

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_api_tools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("http_method", sa.String(10), nullable=False, server_default="GET"),
        sa.Column("url_template", sa.String(2000), nullable=False),
        sa.Column("headers_encrypted", sa.Text(), nullable=True),
        sa.Column("query_params_schema", JSONB(), nullable=True),
        sa.Column("body_schema", JSONB(), nullable=True),
        sa.Column("response_jmespath", sa.String(500), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tenant_api_tools_tenant_id", "tenant_api_tools", ["tenant_id"])
    op.create_unique_constraint("uq_tenant_api_tool_name", "tenant_api_tools", ["tenant_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_tenant_api_tool_name", "tenant_api_tools", type_="unique")
    op.drop_index("ix_tenant_api_tools_tenant_id", table_name="tenant_api_tools")
    op.drop_table("tenant_api_tools")
