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

    def test_auto_policy_instruction_matches_user_language(self):
        instruction = self.service.build_lang_instruction("ko", policy="auto")
        # auto 정책은 사용자 언어에 맞춰 답변하도록 지시
        assert "user" in instruction.lower()
        assert "language" in instruction.lower()
        # 고정 언어 지시가 아니어야 함
        assert "반드시 한국어" not in instruction

    def test_auto_policy_same_instruction_regardless_of_lang_code(self):
        instr_ko = self.service.build_lang_instruction("ko", policy="auto")
        instr_en = self.service.build_lang_instruction("en", policy="auto")
        assert instr_ko == instr_en  # auto는 lang_code 무관하게 동일한 지시문

    def test_fixed_policy_instruction_is_strict(self):
        instruction = self.service.build_lang_instruction("ko", policy="fixed")
        assert "한국어" in instruction or "Korean" in instruction
        # fixed는 반드시/must 포함
        assert "반드시" in instruction or "must" in instruction.lower()

    def test_whitelist_policy_instruction_lists_allowed_langs(self):
        instruction = self.service.build_lang_instruction(
            "ko", policy="whitelist", allowed_langs=["ko", "en"]
        )
        assert "Korean" in instruction
        assert "English" in instruction

    def test_whitelist_policy_instruction_includes_fallback(self):
        instruction = self.service.build_lang_instruction(
            "ko", policy="whitelist", allowed_langs=["ko", "en"]
        )
        # 허용 목록 외 언어는 기본 언어로 폴백
        assert "Korean" in instruction  # default fallback lang
