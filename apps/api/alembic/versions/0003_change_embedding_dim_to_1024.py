"""change embedding dimension from 768 to 1024

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""

from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD_DIM = 768
NEW_DIM = 1024


def upgrade() -> None:
    # ivfflat 인덱스는 컬럼 타입에 종속되므로 먼저 삭제
    op.drop_index("ix_chunks_tenant_embedding", table_name="chunks")

    # 기존 청크 데이터 삭제 (차원이 다르면 기존 벡터 재사용 불가)
    op.execute("DELETE FROM chunks")
    # 청크 삭제에 따라 documents 상태도 초기화
    op.execute("UPDATE documents SET status='pending', chunk_count=0, error_message=NULL")

    # 컬럼 타입 변경
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({NEW_DIM})")

    # 인덱스 재생성
    op.execute(
        """
        CREATE INDEX ix_chunks_tenant_embedding
        ON chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_tenant_embedding", table_name="chunks")
    op.execute("DELETE FROM chunks")
    op.execute("UPDATE documents SET status='pending', chunk_count=0, error_message=NULL")
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({OLD_DIM})")
    op.execute(
        """
        CREATE INDEX ix_chunks_tenant_embedding
        ON chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
