"""Phase 1 RED: Entity/Relationship ORM 모델 구조 검증.

실제 DB 없이 SQLAlchemy metadata를 통해 테이블/컬럼/제약 조건을 검증한다.
"""

import pytest

from app.db.base import Base


@pytest.mark.unit
class TestEntityModel:
    def test_entity_model_is_importable(self):
        from app.models.entity import Entity  # noqa: F401

    def test_entity_table_registered(self):
        from app.models.entity import Entity  # noqa: F401

        assert "entities" in Base.metadata.tables

    def test_entity_has_required_columns(self):
        from app.models.entity import Entity

        cols = {c.name for c in Entity.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "name",
            "entity_type",
            "description",
            "description_embedding",
            "source_chunk_ids",
            "created_at",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"

    def test_entity_tenant_fk_cascades(self):
        from app.models.entity import Entity

        tenant_col = Entity.__table__.columns["tenant_id"]
        fks = list(tenant_col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].ondelete == "CASCADE"
        assert "tenants.id" in str(fks[0].target_fullname)

    def test_entity_has_unique_merge_key(self):
        """동일 테넌트 내 (lower(name), entity_type)는 UNIQUE여야 병합 가능."""
        from app.models.entity import Entity

        constraints = Entity.__table__.constraints
        uniques = [c for c in constraints if c.__class__.__name__ == "UniqueConstraint"]
        indexes = list(Entity.__table__.indexes)
        # UNIQUE는 constraint 또는 index 로 표현 가능
        cols_sets = [
            tuple(sorted(c.name for c in u.columns))
            for u in uniques
        ] + [
            tuple(sorted(c.name for c in i.columns))
            for i in indexes if i.unique
        ]
        assert any(
            "tenant_id" in s and "entity_type" in s and "name" in s
            for s in cols_sets
        ), f"UNIQUE on (tenant_id, name, entity_type) missing; got {cols_sets}"

    def test_entity_name_and_type_not_null(self):
        from app.models.entity import Entity

        assert Entity.__table__.columns["name"].nullable is False
        assert Entity.__table__.columns["entity_type"].nullable is False
        assert Entity.__table__.columns["tenant_id"].nullable is False


@pytest.mark.unit
class TestRelationshipModel:
    def test_relationship_model_is_importable(self):
        from app.models.relationship import Relationship  # noqa: F401

    def test_relationship_table_registered(self):
        from app.models.relationship import Relationship  # noqa: F401

        assert "relationships" in Base.metadata.tables

    def test_relationship_has_required_columns(self):
        from app.models.relationship import Relationship

        cols = {c.name for c in Relationship.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "source_entity_id",
            "target_entity_id",
            "description",
            "keywords",
            "description_embedding",
            "weight",
            "source_chunk_ids",
            "created_at",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"

    def test_relationship_fks_cascade(self):
        from app.models.relationship import Relationship

        for col_name, target in (
            ("tenant_id", "tenants.id"),
            ("source_entity_id", "entities.id"),
            ("target_entity_id", "entities.id"),
        ):
            col = Relationship.__table__.columns[col_name]
            fks = list(col.foreign_keys)
            assert len(fks) == 1, f"{col_name} missing FK"
            assert target in str(fks[0].target_fullname)
            assert fks[0].ondelete == "CASCADE"

    def test_relationship_has_tenant_source_index(self):
        from app.models.relationship import Relationship

        index_cols = [
            tuple(c.name for c in i.columns) for i in Relationship.__table__.indexes
        ]
        assert any(
            "tenant_id" in cols and "source_entity_id" in cols for cols in index_cols
        ), f"tenant+source index missing; got {index_cols}"
        assert any(
            "tenant_id" in cols and "target_entity_id" in cols for cols in index_cols
        ), f"tenant+target index missing; got {index_cols}"


@pytest.mark.unit
class TestTenantGraphRelationships:
    def test_tenant_has_entities_relationship(self):
        from app.models.tenant import Tenant

        assert "entities" in Tenant.__mapper__.relationships

    def test_tenant_has_relationships_relationship(self):
        from app.models.tenant import Tenant

        assert "relationships" in Tenant.__mapper__.relationships
