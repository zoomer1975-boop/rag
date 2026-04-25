"""message 토큰/레이턴시 통계 컬럼 추가

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "latency_ms")
    op.drop_column("messages", "output_tokens")
    op.drop_column("messages", "input_tokens")
