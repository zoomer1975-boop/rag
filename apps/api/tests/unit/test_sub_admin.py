"""부관리자 모델 단위 테스트 (TDD)"""

import pytest
from app.models.sub_admin import SubAdmin


class TestSubAdminPasswordHandling:
    """비밀번호 해싱 및 검증 테스트"""

    def test_password_hash_and_verify_correct_password(self):
        """비밀번호 해싱 후 올바른 비밀번호 검증"""
        plain_password = "SecurePass123"
        hashed = SubAdmin.hash_password(plain_password)

        # 해시된 비밀번호는 평문이 아니어야 함
        assert hashed != plain_password
        assert len(hashed) > 0

        # 같은 평문으로는 같은 부관리자 검증 메서드로 확인
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash=hashed,
        )
        assert sub_admin.verify_password(plain_password)

    def test_wrong_password_fails_verification(self):
        """틀린 비밀번호 검증 실패"""
        plain_password = "SecurePass123"
        wrong_password = "WrongPass456"
        hashed = SubAdmin.hash_password(plain_password)

        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash=hashed,
        )
        assert not sub_admin.verify_password(wrong_password)

    def test_empty_password_verification_fails(self):
        """빈 비밀번호 검증 실패"""
        hashed = SubAdmin.hash_password("password")
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash=hashed,
        )
        assert not sub_admin.verify_password("")


class TestSubAdminIPAllowance:
    """IP 주소 허용 검증 테스트"""

    def test_ip_allowed_empty_allowed_ips_allows_all(self):
        """빈 allowed_ips는 모든 IP 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="",
        )
        assert sub_admin.is_ip_allowed("192.168.1.1")
        assert sub_admin.is_ip_allowed("10.0.0.1")
        assert sub_admin.is_ip_allowed("127.0.0.1")
        assert sub_admin.is_ip_allowed("any-random-ip")

    def test_ip_allowed_single_exact_ip_match(self):
        """정확한 IP 주소 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="192.168.1.100",
        )
        assert sub_admin.is_ip_allowed("192.168.1.100")

    def test_ip_blocked_different_ip(self):
        """다른 IP 거부"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="192.168.1.100",
        )
        assert not sub_admin.is_ip_allowed("192.168.1.101")
        assert not sub_admin.is_ip_allowed("10.0.0.1")

    def test_ip_allowed_single_cidr_range(self):
        """CIDR 범위 내 IP 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="192.168.1.0/24",
        )
        assert sub_admin.is_ip_allowed("192.168.1.1")
        assert sub_admin.is_ip_allowed("192.168.1.100")
        assert sub_admin.is_ip_allowed("192.168.1.255")
        assert not sub_admin.is_ip_allowed("192.168.2.1")

    def test_ip_allowed_multiple_ips_comma_separated(self):
        """쉼표로 구분된 여러 IP 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="192.168.1.100,10.0.0.1,172.16.0.0/12",
        )
        assert sub_admin.is_ip_allowed("192.168.1.100")
        assert sub_admin.is_ip_allowed("10.0.0.1")
        assert sub_admin.is_ip_allowed("172.16.0.5")
        assert not sub_admin.is_ip_allowed("8.8.8.8")

    def test_ip_allowed_ipv6_address(self):
        """IPv6 주소 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="2001:db8::1",
        )
        assert sub_admin.is_ip_allowed("2001:db8::1")
        assert not sub_admin.is_ip_allowed("2001:db8::2")

    def test_ip_allowed_ipv6_cidr(self):
        """IPv6 CIDR 범위 허용"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="2001:db8::/32",
        )
        assert sub_admin.is_ip_allowed("2001:db8::1")
        assert sub_admin.is_ip_allowed("2001:db8:1234::5678")
        assert not sub_admin.is_ip_allowed("2001:db9::1")

    def test_ip_allowed_whitespace_handling(self):
        """공백 문자 무시"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="  192.168.1.100  ,  10.0.0.0/8  ",
        )
        assert sub_admin.is_ip_allowed("192.168.1.100")
        assert sub_admin.is_ip_allowed("10.0.0.5")

    def test_ip_allowed_invalid_ip_does_not_crash(self):
        """유효하지 않은 IP 형식은 안전하게 처리"""
        sub_admin = SubAdmin(
            name="Test Admin",
            username="testadmin",
            password_hash="hashed",
            allowed_ips="invalid-ip,192.168.1.100",
        )
        # 유효한 IP는 통과
        assert sub_admin.is_ip_allowed("192.168.1.100")
        # 유효하지 않은 IP는 거부
        assert not sub_admin.is_ip_allowed("999.999.999.999")
