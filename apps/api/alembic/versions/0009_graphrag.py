"""graphrag: add entities and relationships tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-18
"""

import os

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("description_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "source_chunk_ids",
            ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "name", "entity_type", name="uq_entity_tenant_name_type"
        ),
    )
    op.create_index("ix_entities_tenant_id", "entities", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_entities_description_embedding ON entities "
        "USING ivfflat (description_embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )

    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "keywords", ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("description_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "source_chunk_ids",
            ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_relationships_tenant_id", "relationships", ["tenant_id"]
    )
    op.create_index(
        "ix_relationships_tenant_source",
        "relationships",
        ["tenant_id", "source_entity_id"],
    )
    op.create_index(
        "ix_relationships_tenant_target",
        "relationships",
        ["tenant_id", "target_entity_id"],
    )
    op.execute(
        "CREATE INDEX ix_relationships_description_embedding ON relationships "
        "USING ivfflat (description_embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_relationships_description_embedding")
    op.drop_index("ix_relationships_tenant_target", table_name="relationships")
    op.drop_index("ix_relationships_tenant_source", table_name="relationships")
    op.drop_index("ix_relationships_tenant_id", table_name="relationships")
    op.drop_table("relationships")

    op.execute("DROP INDEX IF EXISTS ix_entities_description_embedding")
    op.drop_index("ix_entities_tenant_id", table_name="entities")
    op.drop_table("entities")
