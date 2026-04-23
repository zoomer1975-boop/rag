"""pii_config enabled 기본값 true로 변경

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-23
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE tenants
        SET pii_config = jsonb_set(pii_config, '{enabled}', 'true')
        WHERE pii_config->>'enabled' = 'false'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE tenants
        SET pii_config = jsonb_set(pii_config, '{enabled}', 'false')
        WHERE pii_config->>'enabled' = 'true'
    """)
