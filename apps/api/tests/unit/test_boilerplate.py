"""상용문구 제거 서비스 단위 테스트"""

import re
import pytest

from app.services.boilerplate import _CompiledPattern, apply, validate_pattern


# ─── apply ────────────────────────────────────────────────────────────────────


def _lit(value: str, pid: int = 1) -> _CompiledPattern:
    return _CompiledPattern(id=pid, kind="literal", value=value)


def _rx(pattern: str, pid: int = 1) -> _CompiledPattern:
    return _CompiledPattern(id=pid, kind="regex", value=re.compile(pattern))


class TestApply:
    def test_no_patterns_returns_original(self):
        assert apply("hello world", []) == "hello world"

    def test_literal_removes_exact_match(self):
        result = apply("Copyright 2024 ACME Corp. Some content.", [_lit("Copyright 2024 ACME Corp.")])
        assert "Copyright 2024 ACME Corp." not in result
        assert "Some content." in result

    def test_literal_multiple_occurrences_all_removed(self):
        result = apply("spam spam spam", [_lit("spam")])
        assert "spam" not in result

    def test_regex_removes_match(self):
        result = apply("Contact us at 010-1234-5678 for help.", [_rx(r"\d{3}-\d{4}-\d{4}")])
        assert "010-1234-5678" not in result
        assert "Contact us at" in result

    def test_multiple_patterns_applied_in_order(self):
        patterns = [_lit("HEADER\n", 1), _lit("FOOTER\n", 2)]
        text = "HEADER\nBody content.\nFOOTER\n"
        result = apply(text, patterns)
        assert "HEADER" not in result
        assert "FOOTER" not in result
        assert "Body content." in result

    def test_excessive_blank_lines_collapsed(self):
        # blank-line normalisation runs when at least one pattern is present
        text = "Line1\n\n\n\n\nLine2"
        result = apply(text, [_lit("NOOP_XYZ")])
        assert "\n\n\n" not in result
        assert "Line1" in result
        assert "Line2" in result

    def test_result_is_stripped(self):
        # strip() runs when at least one pattern is present
        result = apply("  hello  ", [_lit("NOOP_XYZ")])
        assert result == "hello"

    def test_empty_text_after_removal(self):
        result = apply("remove me", [_lit("remove me")])
        assert result == ""

    def test_pattern_error_skipped_gracefully(self):
        # regex pattern that errors on sub (shouldn't happen with compiled patterns,
        # but guard is in place)
        bad = _CompiledPattern(id=99, kind="literal", value="safe")
        result = apply("safe text here", [bad])
        assert "text here" in result


# ─── validate_pattern ─────────────────────────────────────────────────────────


class TestValidatePattern:
    def test_valid_literal_returns_none(self):
        assert validate_pattern("literal", "Copyright notice") is None

    def test_valid_regex_returns_none(self):
        assert validate_pattern("regex", r"\d{3}-\d{4}-\d{4}") is None

    def test_empty_pattern_returns_error(self):
        err = validate_pattern("literal", "   ")
        assert err is not None
        assert "빈 문자열" in err

    def test_pattern_too_long_returns_error(self):
        err = validate_pattern("literal", "x" * 2001)
        assert err is not None
        assert "2000" in err

    def test_invalid_regex_returns_error(self):
        err = validate_pattern("regex", "[invalid(")
        assert err is not None
        assert "정규식" in err

    def test_redos_pattern_returns_error(self):
        err = validate_pattern("regex", r"(a+)+")
        assert err is not None
        assert "ReDoS" in err

    def test_literal_type_skips_regex_validation(self):
        # "[invalid(" is a valid literal string
        assert validate_pattern("literal", "[invalid(") is None

    def test_pattern_exactly_at_max_length_is_valid(self):
        assert validate_pattern("literal", "x" * 2000) is None
