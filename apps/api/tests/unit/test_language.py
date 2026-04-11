"""언어 감지 서비스 단위 테스트 (TDD - RED 단계)"""

import pytest

from app.services.language import LanguageService


class TestLanguageService:
    def setup_method(self):
        self.service = LanguageService(default_language="ko")

    # ─── parse_accept_language ───────────────────────────────────────────────

    def test_parse_full_locale_returns_base_lang(self):
        assert self.service.parse_accept_language("ko-KR") == "ko"

    def test_parse_en_us_returns_en(self):
        assert self.service.parse_accept_language("en-US") == "en"

    def test_parse_bare_code_returns_itself(self):
        assert self.service.parse_accept_language("ja") == "ja"

    def test_parse_empty_returns_default(self):
        assert self.service.parse_accept_language("") == "ko"

    def test_parse_none_returns_default(self):
        assert self.service.parse_accept_language(None) == "ko"

    def test_parse_unknown_lang_returns_default(self):
        assert self.service.parse_accept_language("xx-XX") == "ko"

    def test_parse_header_with_quality_values(self):
        # Accept-Language: ko-KR,ko;q=0.9,en-US;q=0.8
        result = self.service.parse_accept_language("ko-KR,ko;q=0.9,en-US;q=0.8")
        assert result == "ko"

    def test_parse_english_first_header(self):
        result = self.service.parse_accept_language("en-US,en;q=0.9,ko;q=0.8")
        assert result == "en"

    # ─── resolve_lang (테넌트 정책 적용) ────────────────────────────────────

    def test_auto_policy_returns_detected_lang(self):
        result = self.service.resolve_lang(
            detected="en",
            policy="auto",
            default_lang="ko",
            allowed_langs=["ko", "en", "ja"],
        )
        assert result == "en"

    def test_fixed_policy_always_returns_default(self):
        result = self.service.resolve_lang(
            detected="en",
            policy="fixed",
            default_lang="ko",
            allowed_langs=["ko", "en"],
        )
        assert result == "ko"

    def test_whitelist_policy_allows_listed_lang(self):
        result = self.service.resolve_lang(
            detected="ja",
            policy="whitelist",
            default_lang="ko",
            allowed_langs=["ko", "en", "ja"],
        )
        assert result == "ja"

    def test_whitelist_policy_falls_back_for_unlisted(self):
        result = self.service.resolve_lang(
            detected="fr",
            policy="whitelist",
            default_lang="ko",
            allowed_langs=["ko", "en"],
        )
        assert result == "ko"

    # ─── build_lang_instruction ──────────────────────────────────────────────

    def test_instruction_for_korean(self):
        instruction = self.service.build_lang_instruction("ko")
        assert "한국어" in instruction or "Korean" in instruction

    def test_instruction_for_english(self):
        instruction = self.service.build_lang_instruction("en")
        assert "English" in instruction

    def test_instruction_for_japanese(self):
        instruction = self.service.build_lang_instruction("ja")
        assert "日本語" in instruction or "Japanese" in instruction

    def test_instruction_for_unknown_lang_returns_generic(self):
        instruction = self.service.build_lang_instruction("xx")
        assert len(instruction) > 0
