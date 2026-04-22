"""대화 암호화 서비스 단위 테스트 (TDD)"""

import pytest

from app.services.conv_encryption import ConversationEncryptor

SECRET = "test-secret-key-that-is-long-enough-for-hkdf-derivation"
encryptor = ConversationEncryptor(SECRET)


# ─── MEK 파생 ─────────────────────────────────────────────────────────────────

class TestMekDerivation:
    def test_mek_is_32_bytes(self):
        mek = ConversationEncryptor._derive_mek(SECRET)
        assert len(mek) == 32

    def test_mek_is_deterministic(self):
        mek1 = ConversationEncryptor._derive_mek(SECRET)
        mek2 = ConversationEncryptor._derive_mek(SECRET)
        assert mek1 == mek2

    def test_different_secrets_yield_different_mek(self):
        mek1 = ConversationEncryptor._derive_mek("secret-a")
        mek2 = ConversationEncryptor._derive_mek("secret-b")
        assert mek1 != mek2


# ─── DEK 생성 및 래핑 ─────────────────────────────────────────────────────────

class TestDekWrapping:
    def test_dek_is_32_bytes(self):
        dek = encryptor.generate_dek()
        assert len(dek) == 32

    def test_dek_is_random(self):
        dek1 = encryptor.generate_dek()
        dek2 = encryptor.generate_dek()
        assert dek1 != dek2

    def test_wrap_unwrap_roundtrip(self):
        dek = encryptor.generate_dek()
        wrapped = encryptor.wrap_dek(dek)
        recovered = encryptor.unwrap_dek(wrapped)
        assert recovered == dek

    def test_wrapped_is_base64_string(self):
        import base64
        dek = encryptor.generate_dek()
        wrapped = encryptor.wrap_dek(dek)
        assert isinstance(wrapped, str)
        decoded = base64.b64decode(wrapped)
        # nonce(12) + ciphertext(32) + tag(16) = 60 bytes
        assert len(decoded) == 60

    def test_different_wraps_are_different(self):
        dek = encryptor.generate_dek()
        w1 = encryptor.wrap_dek(dek)
        w2 = encryptor.wrap_dek(dek)
        assert w1 != w2  # nonce가 매번 다름

    def test_tampered_wrapped_dek_raises(self):
        import base64
        dek = encryptor.generate_dek()
        wrapped = encryptor.wrap_dek(dek)
        raw = bytearray(base64.b64decode(wrapped))
        raw[-1] ^= 0xFF  # 마지막 바이트 변조
        tampered = base64.b64encode(bytes(raw)).decode()
        with pytest.raises(Exception):
            encryptor.unwrap_dek(tampered)


# ─── 메시지 암호화/복호화 ──────────────────────────────────────────────────────

class TestMessageEncryption:
    def setup_method(self):
        self.dek = encryptor.generate_dek()

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "안녕하세요. 학번은 2024001이고 이름은 홍길동님입니다."
        ct = encryptor.encrypt(plaintext, self.dek)
        recovered = encryptor.decrypt(ct, self.dek)
        assert recovered == plaintext

    def test_empty_string_roundtrip(self):
        ct = encryptor.encrypt("", self.dek)
        assert encryptor.decrypt(ct, self.dek) == ""

    def test_ciphertext_is_base64_string(self):
        import base64
        ct = encryptor.encrypt("hello", self.dek)
        assert isinstance(ct, str)
        base64.b64decode(ct)  # 예외 없으면 성공

    def test_same_plaintext_different_ciphertexts(self):
        msg = "동일 메시지"
        ct1 = encryptor.encrypt(msg, self.dek)
        ct2 = encryptor.encrypt(msg, self.dek)
        assert ct1 != ct2  # nonce randomness

    def test_wrong_dek_raises(self):
        ct = encryptor.encrypt("secret", self.dek)
        other_dek = encryptor.generate_dek()
        with pytest.raises(Exception):
            encryptor.decrypt(ct, other_dek)

    def test_tampered_ciphertext_raises(self):
        import base64
        ct = encryptor.encrypt("secret", self.dek)
        raw = bytearray(base64.b64decode(ct))
        raw[-1] ^= 0xFF
        tampered = base64.b64encode(bytes(raw)).decode()
        with pytest.raises(Exception):
            encryptor.decrypt(tampered, self.dek)

    def test_unicode_content(self):
        texts = [
            "日本語テスト",
            "中文测试",
            "한국어 테스트 — 이름: [이름] 전화: [전화번호]",
            "Emoji 🎉🔐",
        ]
        for text in texts:
            ct = encryptor.encrypt(text, self.dek)
            assert encryptor.decrypt(ct, self.dek) == text

    def test_long_message(self):
        long_text = "가나다라마바사아자차카타파하" * 500  # ~7000 chars
        ct = encryptor.encrypt(long_text, self.dek)
        assert encryptor.decrypt(ct, self.dek) == long_text


# ─── DEK 캐시 ─────────────────────────────────────────────────────────────────

class TestDekCache:
    def test_cache_stores_and_retrieves_dek(self):
        e = ConversationEncryptor(SECRET)
        dek = e.generate_dek()
        e._set_cache(tenant_id=1, dek=dek)
        assert e._get_cache(tenant_id=1) == dek

    def test_cache_miss_returns_none(self):
        e = ConversationEncryptor(SECRET)
        assert e._get_cache(tenant_id=999) is None

    def test_cache_evicts_expired(self):
        import time
        e = ConversationEncryptor(SECRET, cache_ttl_seconds=0)
        dek = e.generate_dek()
        e._set_cache(tenant_id=2, dek=dek)
        time.sleep(0.01)
        assert e._get_cache(tenant_id=2) is None
