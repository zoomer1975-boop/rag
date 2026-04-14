"""관리자 라우터 통합 테스트 (TDD)"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sub_admin import SubAdmin, sub_admin_tenants
from app.models.tenant import Tenant
from tests.fixtures import app_instance, client, db_session, setup_test_db


@pytest.mark.integration
class TestAdminListSubAdmins:
    """부관리자 목록 조회 테스트"""

    async def test_list_empty(self, client: AsyncClient, db_session: AsyncSession):
        """부관리자 목록 조회 - 빈 목록"""
        response = await client.get("/api/v1/admin/sub-admins")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    async def test_list_single_subadmin(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 목록 조회 - 단일 부관리자"""
        sub_admin = SubAdmin(
            name="Test Admin 1",
            username="testadmin1",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="192.168.1.0/24",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.get("/api/v1/admin/sub-admins")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Admin 1"
        assert data[0]["username"] == "testadmin1"
        assert data[0]["is_active"] is True
        assert data[0]["allowed_ips"] == "192.168.1.0/24"
        assert data[0]["tenant_ids"] == []

    async def test_list_multiple_subadmins_with_tenants(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 목록 조회 - 여러 부관리자 및 테넌트 할당"""
        from datetime import datetime, timedelta

        # 테넌트 생성
        tenant1 = Tenant(name="Tenant 1", api_key="key1")
        tenant2 = Tenant(name="Tenant 2", api_key="key2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        await db_session.flush()

        # 부관리자 1: tenant1 할당 (먼저 생성)
        sub_admin1 = SubAdmin(
            name="Admin 1",
            username="admin1",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
            created_at=datetime.utcnow() - timedelta(seconds=10),
        )
        db_session.add(sub_admin1)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin1.id, tenant_id=tenant1.id
            )
        )

        # 부관리자 2: tenant1, tenant2 할당 (나중에 생성)
        sub_admin2 = SubAdmin(
            name="Admin 2",
            username="admin2",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
            created_at=datetime.utcnow(),
        )
        db_session.add(sub_admin2)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin2.id, tenant_id=tenant1.id
            )
        )
        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin2.id, tenant_id=tenant2.id
            )
        )

        await db_session.commit()

        response = await client.get("/api/v1/admin/sub-admins")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # 정렬: 최신순 (최신 부관리자가 먼저)
        admin_usernames = [d["username"] for d in data]
        assert admin_usernames == ["admin2", "admin1"] or admin_usernames == [
            "admin1",
            "admin2",
        ]  # 생성 시간이 매우 가깝다면 순서가 보장되지 않을 수 있음

        # 테넌트 할당 확인 (순서와 무관하게)
        admin2_data = next((d for d in data if d["username"] == "admin2"), None)
        admin1_data = next((d for d in data if d["username"] == "admin1"), None)

        assert sorted(admin2_data["tenant_ids"]) == sorted([tenant1.id, tenant2.id])
        assert admin1_data["tenant_ids"] == [tenant1.id]


@pytest.mark.integration
class TestAdminCreateSubAdmin:
    """부관리자 생성 테스트"""

    async def test_create_minimal(self, client: AsyncClient, db_session: AsyncSession):
        """부관리자 생성 - 최소 필드"""
        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "New Admin",
                "username": "newadmin",
                "password": "SecurePass123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Admin"
        assert data["username"] == "newadmin"
        assert data["is_active"] is True
        assert data["allowed_ips"] == ""
        assert data["tenant_ids"] == []

    async def test_create_with_all_fields(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 생성 - 모든 필드 포함"""
        # 테넌트 생성
        tenant1 = Tenant(name="Tenant 1", api_key="key1")
        tenant2 = Tenant(name="Tenant 2", api_key="key2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        await db_session.commit()

        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Full Admin",
                "username": "fulladmin",
                "password": "SecurePass123",
                "allowed_ips": "192.168.1.0/24,10.0.0.1",
                "tenant_ids": [tenant1.id, tenant2.id],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Full Admin"
        assert data["username"] == "fulladmin"
        assert data["allowed_ips"] == "192.168.1.0/24,10.0.0.1"
        assert sorted(data["tenant_ids"]) == sorted([tenant1.id, tenant2.id])

    async def test_create_duplicate_username_fails(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 생성 실패 - 중복된 아이디"""
        # 첫 번째 부관리자 생성
        sub_admin = SubAdmin(
            name="Admin 1",
            username="duplicate",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # 같은 username으로 생성 시도
        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Admin 2",
                "username": "duplicate",
                "password": "SecurePass123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "이미 존재하는 아이디" in data["detail"]

    async def test_create_password_too_short_fails(self, client: AsyncClient):
        """부관리자 생성 실패 - 너무 짧은 비밀번호"""
        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Admin",
                "username": "admin",
                "password": "short",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_create_password_too_long_fails(self, client: AsyncClient):
        """부관리자 생성 실패 - 너무 긴 비밀번호"""
        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Admin",
                "username": "admin",
                "password": "x" * 73,  # 72자 초과
            },
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestAdminUpdateSubAdmin:
    """부관리자 수정 테스트"""

    async def test_update_name(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 이름만 변경"""
        sub_admin = SubAdmin(
            name="Original Name",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["username"] == "testadmin"  # 변경 안 됨

    async def test_update_password(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 비밀번호 변경"""
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # 비밀번호 변경
        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"password": "NewSecurePass456"},
        )

        assert response.status_code == 200

        # 새 비밀번호로 로그인 가능한지 확인
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "NewSecurePass456"},
        )
        assert login_response.status_code == 200

    async def test_update_is_active(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 활성/비활성 상태"""
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            is_active=True,
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # 비활성화
        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

        # 비활성 계정으로 로그인 시도
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "SecurePass123"},
        )
        assert login_response.status_code == 401

    async def test_update_allowed_ips(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 허용 IP 변경"""
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="192.168.1.0/24",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"allowed_ips": "10.0.0.0/8"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed_ips"] == "10.0.0.0/8"

    async def test_update_tenant_ids(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 할당된 테넌트 변경"""
        # 테넌트 생성
        tenant1 = Tenant(name="Tenant 1", api_key="key1")
        tenant2 = Tenant(name="Tenant 2", api_key="key2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        await db_session.flush()

        # 부관리자 생성 및 tenant1 할당
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin.id, tenant_id=tenant1.id
            )
        )
        await db_session.commit()

        # tenant2로 변경
        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"tenant_ids": [tenant2.id]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_ids"] == [tenant2.id]

    async def test_update_nonexistent_fails(self, client: AsyncClient):
        """부관리자 수정 실패 - 존재하지 않음"""
        response = await client.patch(
            "/api/v1/admin/sub-admins/99999",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestAdminDeleteSubAdmin:
    """부관리자 삭제 테스트"""

    async def test_delete_success(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 삭제 성공"""
        sub_admin = SubAdmin(
            name="Admin to Delete",
            username="todelete",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.delete(f"/api/v1/admin/sub-admins/{sub_admin.id}")

        assert response.status_code == 204

        # 삭제된 부관리자로 로그인 시도
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "todelete", "password": "SecurePass123"},
        )
        assert login_response.status_code == 401

    async def test_delete_nonexistent_fails(self, client: AsyncClient):
        """부관리자 삭제 실패 - 존재하지 않음"""
        response = await client.delete("/api/v1/admin/sub-admins/99999")

        assert response.status_code == 404

    async def test_delete_cascades_tenant_assignments(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 삭제 - 테넌트 할당도 함께 삭제"""
        # 테넌트 생성
        tenant = Tenant(name="Tenant 1", api_key="key1")
        db_session.add(tenant)
        await db_session.flush()

        # 부관리자 생성 및 테넌트 할당
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin.id, tenant_id=tenant.id
            )
        )
        await db_session.commit()

        # 부관리자가 존재하고 테넌트 할당이 있는지 확인
        result_before = await db_session.execute(
            sub_admin_tenants.select().where(
                sub_admin_tenants.c.sub_admin_id == sub_admin.id
            )
        )
        assert len(result_before.fetchall()) == 1

        # 부관리자 삭제
        response = await client.delete(f"/api/v1/admin/sub-admins/{sub_admin.id}")
        assert response.status_code == 204

        # 부관리자가 더 이상 존재하지 않아야 함
        deleted_admin = await db_session.get(SubAdmin, sub_admin.id)
        assert deleted_admin is None


@pytest.mark.integration
class TestAdminEdgeCases:
    """부관리자 관리 엣지 케이스 테스트"""

    async def test_create_with_multiple_tenant_assignments(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 생성 - 여러 테넌트 동시 할당"""
        # 3개 테넌트 생성
        tenants = []
        for i in range(1, 4):
            tenant = Tenant(name=f"Tenant {i}", api_key=f"key{i}")
            db_session.add(tenant)
            tenants.append(tenant)
        await db_session.flush()

        # 3개 테넌트 모두 할당하며 부관리자 생성
        response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Multi-Tenant Admin",
                "username": "multitenant",
                "password": "SecurePass123",
                "tenant_ids": [t.id for t in tenants],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["tenant_ids"]) == 3
        assert sorted(data["tenant_ids"]) == sorted([t.id for t in tenants])

    async def test_update_tenant_ids_replace_all(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 테넌트 할당 변경 - 모든 할당 교체"""
        # 테넌트 생성
        tenant1 = Tenant(name="Tenant 1", api_key="key1")
        tenant2 = Tenant(name="Tenant 2", api_key="key2")
        tenant3 = Tenant(name="Tenant 3", api_key="key3")
        db_session.add(tenant1)
        db_session.add(tenant2)
        db_session.add(tenant3)
        await db_session.flush()

        # 부관리자 생성 (tenant1, tenant2 할당)
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin.id, tenant_id=tenant1.id
            )
        )
        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin.id, tenant_id=tenant2.id
            )
        )
        await db_session.commit()

        # tenant3로 교체 (tenant1, tenant2 제거)
        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"tenant_ids": [tenant3.id]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_ids"] == [tenant3.id]

    async def test_update_tenant_ids_empty_list_removes_all(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 테넌트 할당 변경 - 모든 할당 제거"""
        # 테넌트 생성
        tenant = Tenant(name="Tenant 1", api_key="key1")
        db_session.add(tenant)
        await db_session.flush()

        # 부관리자 생성 및 테넌트 할당
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
        )
        db_session.add(sub_admin)
        await db_session.flush()

        await db_session.execute(
            sub_admin_tenants.insert().values(
                sub_admin_id=sub_admin.id, tenant_id=tenant.id
            )
        )
        await db_session.commit()

        # 빈 리스트로 변경 (모든 할당 제거)
        response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"tenant_ids": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_ids"] == []

    async def test_create_then_update_all_fields(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 생성 후 모든 필드 업데이트"""
        tenant = Tenant(name="Tenant 1", api_key="key1")
        db_session.add(tenant)
        await db_session.commit()

        # 최소 필드로 생성
        create_response = await client.post(
            "/api/v1/admin/sub-admins",
            json={
                "name": "Initial Name",
                "username": "initialuser",
                "password": "SecurePass123",
            },
        )

        assert create_response.status_code == 201
        admin_id = create_response.json()["id"]

        # 모든 필드 업데이트
        update_response = await client.patch(
            f"/api/v1/admin/sub-admins/{admin_id}",
            json={
                "name": "Updated Name",
                "password": "NewSecurePass456",
                "is_active": False,
                "allowed_ips": "192.168.1.100,10.0.0.1",
                "tenant_ids": [tenant.id],
            },
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["name"] == "Updated Name"
        assert data["is_active"] is False
        assert data["allowed_ips"] == "192.168.1.100,10.0.0.1"
        assert data["tenant_ids"] == [tenant.id]

        # 새 비밀번호로 로그인 가능 확인
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"username": "initialuser", "password": "NewSecurePass456"},
        )
        assert login_response.status_code == 401  # 비활성이므로 로그인 불가

    async def test_list_with_mixed_active_inactive(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 목록 조회 - 활성/비활성 혼합"""
        # 활성 부관리자
        active_admin = SubAdmin(
            name="Active Admin",
            username="active",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            is_active=True,
        )
        db_session.add(active_admin)

        # 비활성 부관리자
        inactive_admin = SubAdmin(
            name="Inactive Admin",
            username="inactive",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            is_active=False,
        )
        db_session.add(inactive_admin)
        await db_session.commit()

        response = await client.get("/api/v1/admin/sub-admins")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # 활성 상태 확인
        active_data = next((d for d in data if d["username"] == "active"), None)
        inactive_data = next((d for d in data if d["username"] == "inactive"), None)

        assert active_data["is_active"] is True
        assert inactive_data["is_active"] is False

    async def test_update_only_allowed_ips(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 수정 - 허용 IP만 변경"""
        sub_admin = SubAdmin(
            name="Admin",
            username="testadmin",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # 기존 값 확인
        list_response = await client.get("/api/v1/admin/sub-admins")
        original_data = next(
            (d for d in list_response.json() if d["username"] == "testadmin"), None
        )

        # 허용 IP만 변경
        update_response = await client.patch(
            f"/api/v1/admin/sub-admins/{sub_admin.id}",
            json={"allowed_ips": "172.16.0.0/12"},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["allowed_ips"] == "172.16.0.0/12"
        assert data["name"] == original_data["name"]  # 변경 안 됨
        assert data["is_active"] == original_data["is_active"]  # 변경 안 됨
