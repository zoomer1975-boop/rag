"""인증 라우터 통합 테스트 (TDD)"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from app.config import Settings
from app.models.sub_admin import SubAdmin, sub_admin_tenants
from app.models.tenant import Tenant
from tests.fixtures import app_instance, client, db_session, setup_test_db


@pytest.mark.integration
class TestAuthLoginSuperAdmin:
    """최고관리자 로그인 테스트"""

    async def test_superadmin_login_success(self, client: AsyncClient):
        """최고관리자 로그인 성공"""
        mock_settings = Settings(admin_username="admin", admin_password="secret123")

        with patch("app.routers.auth.get_settings", return_value=mock_settings):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "secret123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["is_superadmin"] is True
            assert data["sub_admin_id"] is None
            assert data["tenant_ids"] is None

    async def test_superadmin_login_wrong_password(self, client: AsyncClient):
        """최고관리자 로그인 실패 - 잘못된 비밀번호"""
        mock_settings = Settings(admin_username="admin", admin_password="secret123")

        with patch("app.routers.auth.get_settings", return_value=mock_settings):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrongpass"},
            )

            assert response.status_code == 401
            data = response.json()
            assert "올바르지 않습니다" in data["detail"]

    async def test_superadmin_login_wrong_username(self, client: AsyncClient):
        """최고관리자 로그인 실패 - 잘못된 아이디"""
        mock_settings = Settings(admin_username="admin", admin_password="secret123")

        with patch("app.routers.auth.get_settings", return_value=mock_settings):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "wronguser", "password": "secret123"},
            )

            assert response.status_code == 401


@pytest.mark.integration
class TestAuthLoginSubAdmin:
    """부관리자 로그인 테스트"""

    async def test_subadmin_login_success(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 성공"""
        # 부관리자 생성
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin1",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin1", "password": "SecurePass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["is_superadmin"] is False
        assert data["sub_admin_id"] == sub_admin.id
        assert data["tenant_ids"] == []

    async def test_subadmin_login_with_assigned_tenants(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 - 할당된 테넌트 포함"""
        # 테넌트 생성
        tenant1 = Tenant(name="Tenant 1", api_key="key1")
        tenant2 = Tenant(name="Tenant 2", api_key="key2")
        db_session.add(tenant1)
        db_session.add(tenant2)
        await db_session.flush()

        # 부관리자 생성
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin2",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.flush()

        # 테넌트 할당
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

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin2", "password": "SecurePass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["is_superadmin"] is False
        assert data["sub_admin_id"] == sub_admin.id
        assert sorted(data["tenant_ids"]) == sorted([tenant1.id, tenant2.id])

    async def test_subadmin_login_inactive_fails(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 실패 - 비활성화된 계정"""
        # 비활성화된 부관리자 생성
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin_inactive",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
            is_active=False,
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin_inactive", "password": "SecurePass123"},
        )

        assert response.status_code == 401

    async def test_subadmin_login_wrong_password(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 실패 - 잘못된 비밀번호"""
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin3",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin3", "password": "WrongPass456"},
        )

        assert response.status_code == 401

    async def test_subadmin_login_ip_restricted_allowed(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 - IP 제한 (허용된 IP)"""
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin_ip",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="192.168.1.100,10.0.0.0/8",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # Mock: 클라이언트 IP를 허용된 범위로 설정하기 위해
        # X-Forwarded-For 헤더 사용
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin_ip", "password": "SecurePass123"},
            headers={"X-Forwarded-For": "192.168.1.100"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    async def test_subadmin_login_ip_restricted_denied(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 - IP 제한 (차단된 IP)"""
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin_ip_denied",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="192.168.1.100",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin_ip_denied", "password": "SecurePass123"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "IP 주소" in data["detail"]

    async def test_subadmin_login_x_real_ip_header(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 - X-Real-IP 헤더 사용"""
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin_realip",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="10.0.0.50",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # X-Real-IP 헤더로 로그인 (X-Forwarded-For 없을 때 사용)
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin_realip", "password": "SecurePass123"},
            headers={"X-Real-IP": "10.0.0.50"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    async def test_subadmin_login_multiple_ips_in_forwarded_for(
        self, client: AsyncClient, db_session: AsyncSession, setup_test_db
    ):
        """부관리자 로그인 - X-Forwarded-For의 첫 번째 IP 검증"""
        sub_admin = SubAdmin(
            name="Test SubAdmin",
            username="subadmin_multi_ip",
            password_hash=SubAdmin.hash_password("SecurePass123"),
            allowed_ips="192.168.1.1",
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # X-Forwarded-For에 여러 IP가 있을 때 첫 번째만 사용
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "subadmin_multi_ip", "password": "SecurePass123"},
            headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.1, 172.16.0.1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    async def test_subadmin_login_nonexistent_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """부관리자 로그인 실패 - 존재하지 않는 사용자"""
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "SecurePass123"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "올바르지 않습니다" in data["detail"]

    async def test_superadmin_login_token_structure(self, client: AsyncClient):
        """최고관리자 로그인 응답 구조 검증"""
        from unittest.mock import patch

        from app.config import Settings

        mock_settings = Settings(admin_username="admin", admin_password="secret123")

        with patch("app.routers.auth.get_settings", return_value=mock_settings):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "secret123"},
            )

            assert response.status_code == 200
            data = response.json()

            # 응답에 필요한 모든 필드가 있는지 확인
            assert "ok" in data
            assert "is_superadmin" in data
            assert "sub_admin_id" in data
            assert "tenant_ids" in data

            # 값이 올바른지 확인
            assert data["ok"] is True
            assert data["is_superadmin"] is True
            assert data["sub_admin_id"] is None
            assert data["tenant_ids"] is None
