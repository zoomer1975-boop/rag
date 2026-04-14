"""관리자 인증 미들웨어 통합 테스트 (TDD)"""

import pytest
from httpx import AsyncClient

from app.middleware.admin_auth import AdminAuth


@pytest.mark.integration
class TestAdminAuth:
    """AdminAuth 클래스 테스트"""

    def test_superadmin_has_tenant_access(self):
        """최고관리자는 모든 테넌트에 접근 가능"""
        admin_auth = AdminAuth(is_superadmin=True)

        assert admin_auth.has_tenant_access(1) is True
        assert admin_auth.has_tenant_access(999) is True
        assert admin_auth.has_tenant_access(0) is True

    def test_subadmin_with_no_tenants_has_no_access(self):
        """할당된 테넌트가 없는 부관리자는 어떤 테넌트도 접근 불가"""
        admin_auth = AdminAuth(is_superadmin=False, sub_admin_id=1, tenant_ids=[])

        assert admin_auth.has_tenant_access(1) is False
        assert admin_auth.has_tenant_access(999) is False

    def test_subadmin_with_assigned_tenants_has_access(self):
        """할당된 테넌트에만 접근 가능"""
        admin_auth = AdminAuth(
            is_superadmin=False, sub_admin_id=1, tenant_ids=[1, 2, 3]
        )

        assert admin_auth.has_tenant_access(1) is True
        assert admin_auth.has_tenant_access(2) is True
        assert admin_auth.has_tenant_access(3) is True
        assert admin_auth.has_tenant_access(4) is False
        assert admin_auth.has_tenant_access(999) is False

    def test_subadmin_with_single_tenant(self):
        """단일 테넌트 할당된 부관리자"""
        admin_auth = AdminAuth(is_superadmin=False, sub_admin_id=42, tenant_ids=[100])

        assert admin_auth.has_tenant_access(100) is True
        assert admin_auth.has_tenant_access(99) is False
        assert admin_auth.has_tenant_access(101) is False

    def test_admin_auth_properties(self):
        """AdminAuth 속성이 올바르게 설정되는지 확인"""
        admin_auth = AdminAuth(
            is_superadmin=False, sub_admin_id=5, tenant_ids=[10, 20, 30]
        )

        assert admin_auth.is_superadmin is False
        assert admin_auth.sub_admin_id == 5
        assert admin_auth.tenant_ids == [10, 20, 30]

    def test_superadmin_auth_properties(self):
        """최고관리자 AdminAuth 속성"""
        admin_auth = AdminAuth(is_superadmin=True)

        assert admin_auth.is_superadmin is True
        assert admin_auth.sub_admin_id is None
        assert admin_auth.tenant_ids == []

    def test_admin_auth_tenant_ids_default_to_empty_list(self):
        """tenant_ids 기본값은 빈 리스트"""
        admin_auth = AdminAuth(is_superadmin=False, sub_admin_id=1)

        assert admin_auth.tenant_ids == []
        assert isinstance(admin_auth.tenant_ids, list)
