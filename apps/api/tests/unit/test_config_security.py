"""config.py 보안 검증 단위 테스트

테스트 대상: apps/api/app/config.py
  - get_settings(): 필수 시크릿이 비어 있거나 기본값이면 ValueError 발생
  - ADMIN_API_TOKEN 이 비어 있으면 서버 기동 차단 (C-1)
"""

import pytest
from unittest.mock import patch


def _make_env(**overrides: str) -> dict[str, str]:
    """테스트용 최소 유효 환경변수 세트를 반환한다."""
    base = {
        "SECRET_KEY": "a" * 32,
        "ADMIN_PASSWORD": "secure-password-123",
        "ADMIN_API_TOKEN": "valid-token-abc",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    }
    base.update(overrides)
    return base


class TestAdminApiTokenRequired:
    """C-1: ADMIN_API_TOKEN 이 비어 있으면 get_settings() 가 ValueError 를 발생시켜야 한다"""

    def test_empty_admin_api_token_raises(self):
        from app.config import get_settings

        get_settings.cache_clear()
        env = _make_env(ADMIN_API_TOKEN="")
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
                get_settings()
        get_settings.cache_clear()

    def test_valid_admin_api_token_does_not_raise(self):
        from app.config import get_settings

        get_settings.cache_clear()
        env = _make_env()
        with patch.dict("os.environ", env, clear=True):
            settings = get_settings()
        get_settings.cache_clear()
        assert settings.admin_api_token == "valid-token-abc"

    def test_missing_admin_api_token_env_var_raises(self):
        """환경변수 자체가 없을 때 (기본값 "" 사용) 도 차단해야 한다"""
        from app.config import get_settings

        get_settings.cache_clear()
        env = {k: v for k, v in _make_env().items() if k != "ADMIN_API_TOKEN"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
                get_settings()
        get_settings.cache_clear()


class TestRequiredSecrets:
    """기존 필수 시크릿 검증이 계속 작동해야 한다"""

    def test_default_secret_key_raises(self):
        from app.config import get_settings

        get_settings.cache_clear()
        env = _make_env(SECRET_KEY="change-me-to-a-random-secret-key")
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                get_settings()
        get_settings.cache_clear()

    def test_default_admin_password_raises(self):
        from app.config import get_settings

        get_settings.cache_clear()
        env = _make_env(ADMIN_PASSWORD="change-me")
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
                get_settings()
        get_settings.cache_clear()
