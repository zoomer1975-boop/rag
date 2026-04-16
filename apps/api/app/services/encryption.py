"""Fernet 대칭 암호화 — headers 등 민감 정보 저장용"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_fernet() -> Fernet:
    """SECRET_KEY에서 Fernet 키를 파생한다 (32바이트 URL-safe base64)."""
    settings = get_settings()
    key_bytes = settings.secret_key.encode()
    derived = hashlib.sha256(key_bytes).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def encrypt(value: str) -> str:
    """문자열을 암호화하여 반환한다."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """암호화된 문자열을 복호화하여 반환한다."""
    return _get_fernet().decrypt(token.encode()).decode()


def mask_header_values(headers: dict) -> dict:
    """응답 반환 시 헤더 값을 마스킹한다 (앞 4자 + ***)."""
    return {
        k: (v[:4] + "***" if len(v) > 4 else "***")
        for k, v in headers.items()
    }
