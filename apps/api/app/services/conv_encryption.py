"""대화 내역 암호화 서비스 — Envelope Encryption (AES-256-GCM)

키 계층:
  MEK (Master Encryption Key): SECRET_KEY → HKDF-SHA256 → 32 bytes
  DEK (Data Encryption Key):   tenant별 32-byte 랜덤 키, MEK로 감싸서 DB에 저장

암호문 포맷 (base64): nonce(12) || ciphertext || GCM-tag(16)
"""

from __future__ import annotations

import base64
import os
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_DEFAULT_CACHE_TTL = 300  # 5분

_encryptor_instance: "ConversationEncryptor | None" = None


def get_encryptor() -> "ConversationEncryptor":
    """앱 전역 싱글턴 ConversationEncryptor를 반환한다."""
    global _encryptor_instance
    if _encryptor_instance is None:
        from app.config import get_settings
        _encryptor_instance = ConversationEncryptor(get_settings().secret_key)
    return _encryptor_instance


class ConversationEncryptor:
    """MEK에서 파생된 DEK로 메시지를 암호화/복호화한다."""

    def __init__(self, secret_key: str, cache_ttl_seconds: float = _DEFAULT_CACHE_TTL):
        self._mek = self._derive_mek(secret_key)
        self._aesgcm_mek = AESGCM(self._mek)
        self._cache: dict[int, tuple[bytes, float]] = {}  # tenant_id -> (dek, expire_at)
        self._cache_ttl = cache_ttl_seconds

    # ── MEK 파생 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _derive_mek(secret_key: str) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"rag-conversation-mek-v1",
        )
        return hkdf.derive(secret_key.encode())

    # ── DEK 생성 / 래핑 ───────────────────────────────────────────────────────

    def generate_dek(self) -> bytes:
        return os.urandom(32)

    def wrap_dek(self, dek: bytes) -> str:
        """DEK를 MEK로 암호화해 base64 문자열로 반환한다."""
        nonce = os.urandom(12)
        ct = self._aesgcm_mek.encrypt(nonce, dek, None)
        return base64.b64encode(nonce + ct).decode()

    def unwrap_dek(self, wrapped: str) -> bytes:
        """base64로 인코딩된 wrapped DEK를 복호화한다."""
        raw = base64.b64decode(wrapped)
        nonce, ct = raw[:12], raw[12:]
        return self._aesgcm_mek.decrypt(nonce, ct, None)

    # ── 메시지 암호화 ─────────────────────────────────────────────────────────

    def encrypt(self, plaintext: str, dek: bytes) -> str:
        """평문 메시지를 DEK로 암호화해 base64 문자열로 반환한다."""
        aesgcm = AESGCM(dek)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt(self, ciphertext: str, dek: bytes) -> str:
        """base64 암호문을 DEK로 복호화해 평문을 반환한다."""
        raw = base64.b64decode(ciphertext)
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(dek)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

    # ── DEK 캐시 (인메모리, TTL 기반) ────────────────────────────────────────

    def _set_cache(self, tenant_id: int, dek: bytes) -> None:
        self._cache[tenant_id] = (dek, time.monotonic() + self._cache_ttl)

    def _get_cache(self, tenant_id: int) -> bytes | None:
        entry = self._cache.get(tenant_id)
        if entry is None:
            return None
        dek, expire_at = entry
        if time.monotonic() > expire_at:
            del self._cache[tenant_id]
            return None
        return dek

    # ── DB 연동: DEK 조회/생성 ────────────────────────────────────────────────

    async def get_or_create_dek(self, tenant_id: int, db) -> bytes:
        """테넌트 DEK를 캐시 → DB → 신규 생성 순으로 가져온다."""
        cached = self._get_cache(tenant_id)
        if cached is not None:
            return cached

        from sqlalchemy import select, update
        from app.models.tenant import Tenant

        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one()

        if tenant.encrypted_dek:
            dek = self.unwrap_dek(tenant.encrypted_dek)
        else:
            dek = self.generate_dek()
            wrapped = self.wrap_dek(dek)
            await db.execute(
                update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(encrypted_dek=wrapped)
            )
            await db.commit()

        self._set_cache(tenant_id, dek)
        return dek

    async def get_dek_readonly(self, tenant_id: int, db) -> bytes | None:
        """DEK 조회 전용 (새로 생성하지 않음). 없으면 None 반환."""
        cached = self._get_cache(tenant_id)
        if cached is not None:
            return cached

        from sqlalchemy import select
        from app.models.tenant import Tenant

        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant is None or not tenant.encrypted_dek:
            return None

        dek = self.unwrap_dek(tenant.encrypted_dek)
        self._set_cache(tenant_id, dek)
        return dek
