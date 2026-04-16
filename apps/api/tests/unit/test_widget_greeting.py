"""위젯 greeting 다국어 선택 로직 단위 테스트 (TDD - RED 단계)"""

import pytest

from app.services.widget_greeting import resolve_greeting


class TestResolveGreetingPlainString:
    """greeting이 단일 문자열일 때 (기존 동작 유지)"""

    def test_plain_string_returned_as_is(self):
        greeting = "안녕하세요! 무엇을 도와드릴까요?"
        assert resolve_greeting(greeting, lang_code="ko") == greeting

    def test_plain_string_ignores_lang(self):
        greeting = "Hello!"
        assert resolve_greeting(greeting, lang_code="en") == greeting
        assert resolve_greeting(greeting, lang_code="ja") == greeting

    def test_empty_string_returns_empty(self):
        assert resolve_greeting("", lang_code="ko") == ""

    def test_none_returns_empty(self):
        assert resolve_greeting(None, lang_code="ko") == ""


class TestResolveGreetingI18nDict:
    """greeting_i18n dict 형식: {"ko": "...", "en": "...", ...}"""

    def setup_method(self):
        self.i18n = {
            "ko": "안녕하세요!",
            "en": "Hello!",
            "ja": "こんにちは！",
        }

    def test_exact_lang_match(self):
        assert resolve_greeting(self.i18n, lang_code="ko") == "안녕하세요!"
        assert resolve_greeting(self.i18n, lang_code="en") == "Hello!"
        assert resolve_greeting(self.i18n, lang_code="ja") == "こんにちは！"

    def test_missing_lang_falls_back_to_first_entry(self):
        """등록되지 않은 언어 → dict의 첫 번째 값으로 폴백"""
        result = resolve_greeting(self.i18n, lang_code="zh")
        assert result in self.i18n.values()

    def test_empty_dict_returns_empty(self):
        assert resolve_greeting({}, lang_code="ko") == ""

    def test_single_entry_dict_always_returned(self):
        single = {"ko": "안녕!"}
        assert resolve_greeting(single, lang_code="en") == "안녕!"

    def test_lang_code_prefix_match(self):
        """'zh-TW' → 'zh' prefix로 매칭"""
        i18n_with_zh = {**self.i18n, "zh": "你好！"}
        assert resolve_greeting(i18n_with_zh, lang_code="zh-TW") == "你好！"

    def test_default_lang_used_when_no_match(self):
        """default_lang 지정 시 매칭 없으면 해당 언어로 폴백"""
        result = resolve_greeting(self.i18n, lang_code="fr", default_lang="en")
        assert result == "Hello!"

    def test_default_lang_fallback_missing_also_falls_back_to_first(self):
        """default_lang도 dict에 없으면 첫 번째 값"""
        result = resolve_greeting(self.i18n, lang_code="fr", default_lang="zh")
        assert result in self.i18n.values()
