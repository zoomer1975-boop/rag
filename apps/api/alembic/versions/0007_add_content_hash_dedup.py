"""add content_hash to chunks for deduplication

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. content_hash 컬럼 추가
    op.add_column(
        "chunks",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )

    # 2. 기존 데이터에 hash 채우기
    op.execute(
        """
        UPDATE chunks
        SET content_hash = encode(sha256(content::bytea), 'hex')
        """
    )

    # 3. NOT NULL 설정
    op.alter_column("chunks", "content_hash", nullable=False)

    # 4. 테넌트 내 중복 청크 제거 (id 가장 낮은 것만 보존)
    op.execute(
        """
        DELETE FROM chunks
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM chunks
            GROUP BY tenant_id, content_hash
        )
        """
    )

    # 5. 유니크 인덱스 추가 (이후 중복 삽입 방지)
    op.create_index(
        "ix_chunks_tenant_content_hash",
        "chunks",
        ["tenant_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_tenant_content_hash", table_name="chunks")
    op.drop_column("chunks", "content_hash")
