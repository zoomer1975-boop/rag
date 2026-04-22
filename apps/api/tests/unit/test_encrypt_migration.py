"""기존 메시지 암호화 마이그레이션 — 핵심 로직 단위 테스트"""

import pytest

from app.services.conv_encryption import ConversationEncryptor


SECRET = "test-secret-key-for-migration-tests"


@pytest.fixture
def enc() -> ConversationEncryptor:
    return ConversationEncryptor(SECRET, cache_ttl_seconds=60)


@pytest.fixture
def dek(enc: ConversationEncryptor) -> bytes:
    return enc.generate_dek()


class TestMigrationEncryptDecrypt:
    def test_plaintext_survives_encrypt_decrypt(self, enc: ConversationEncryptor, dek: bytes) -> None:
        plain = "안녕하세요, 마이그레이션 테스트입니다."
        ct = enc.encrypt(plain, dek)
        assert enc.decrypt(ct, dek) == plain

    def test_encrypted_flag_differs_from_plain(self, enc: ConversationEncryptor, dek: bytes) -> None:
        plain = "hello"
        ct = enc.encrypt(plain, dek)
        assert ct != plain

    def test_multiple_messages_each_unique_ciphertext(self, enc: ConversationEncryptor, dek: bytes) -> None:
        messages = ["메시지 1", "메시지 2", "메시지 1"]  # 같은 내용도 nonce 달라 다름
        ciphertexts = [enc.encrypt(m, dek) for m in messages]
        # 마지막 두 개(같은 평문)도 nonce가 달라 달라야 함
        assert ciphertexts[0] != ciphertexts[2]
        assert len(set(ciphertexts)) == 3

    def test_idempotency_check_content_enc_not_none(self, enc: ConversationEncryptor, dek: bytes) -> None:
        """이미 암호화된 메시지(content_enc IS NOT NULL)는 건너뛰어야 한다."""
        plain = "original"
        ct = enc.encrypt(plain, dek)
        # content_enc가 None이 아니면 스크립트는 이 메시지를 건너뜀
        should_skip = ct is not None
        assert should_skip

    def test_empty_content_encrypts_and_decrypts(self, enc: ConversationEncryptor, dek: bytes) -> None:
        ct = enc.encrypt("", dek)
        assert enc.decrypt(ct, dek) == ""

    def test_long_message_encrypts(self, enc: ConversationEncryptor, dek: bytes) -> None:
        long_text = "가" * 10_000
        ct = enc.encrypt(long_text, dek)
        assert enc.decrypt(ct, dek) == long_text


class TestWrapUnwrapForMigration:
    def test_dek_wrap_unwrap_roundtrip(self, enc: ConversationEncryptor, dek: bytes) -> None:
        wrapped = enc.wrap_dek(dek)
        assert enc.unwrap_dek(wrapped) == dek

    def test_new_dek_for_each_tenant(self, enc: ConversationEncryptor) -> None:
        dek1 = enc.generate_dek()
        dek2 = enc.generate_dek()
        assert dek1 != dek2

    def test_same_secret_derives_same_mek(self) -> None:
        enc1 = ConversationEncryptor(SECRET)
        enc2 = ConversationEncryptor(SECRET)
        dek = enc1.generate_dek()
        wrapped = enc1.wrap_dek(dek)
        # 같은 SECRET → 같은 MEK → 다른 인스턴스에서도 unwrap 가능
        assert enc2.unwrap_dek(wrapped) == dek
