"""도메인 화이트리스트 검증 — 단위 테스트"""

import pytest

from app.services.domain_validation import is_origin_allowed


class TestIsOriginAllowed:
    """is_origin_allowed(origin, allowed_domains) 동작 검증"""

    # ── 빈 화이트리스트(개발 환경) ──────────────────────────────────
    def test_empty_whitelist_allows_any_origin(self):
        assert is_origin_allowed("https://example.com", []) is True

    def test_empty_whitelist_allows_none_origin(self):
        assert is_origin_allowed(None, []) is True

    # ── 정상 매칭 ──────────────────────────────────────────────────
    def test_exact_domain_match(self):
        assert is_origin_allowed("https://example.com", ["example.com"]) is True

    def test_http_scheme_match(self):
        assert is_origin_allowed("http://example.com", ["example.com"]) is True

    def test_subdomain_not_matched_by_root(self):
        assert is_origin_allowed("https://sub.example.com", ["example.com"]) is False

    def test_subdomain_matched_explicitly(self):
        assert is_origin_allowed("https://sub.example.com", ["sub.example.com"]) is True

    def test_port_stripped_before_comparison(self):
        assert is_origin_allowed("https://example.com:8443", ["example.com"]) is True

    def test_port_80_stripped(self):
        assert is_origin_allowed("http://example.com:80", ["example.com"]) is True

    # ── localhost 허용 ──────────────────────────────────────────────
    def test_localhost_matched(self):
        assert is_origin_allowed("http://localhost:3000", ["localhost"]) is True

    def test_localhost_127_matched(self):
        assert is_origin_allowed("http://127.0.0.1:8000", ["127.0.0.1"]) is True

    # ── 차단 케이스 ────────────────────────────────────────────────
    def test_unregistered_domain_blocked(self):
        assert is_origin_allowed("https://evil.com", ["example.com"]) is False

    def test_partial_domain_not_matched(self):
        # attackerexample.com 은 example.com 화이트리스트로 통과하면 안 됨
        assert is_origin_allowed("https://attackerexample.com", ["example.com"]) is False

    def test_none_origin_blocked_when_whitelist_set(self):
        assert is_origin_allowed(None, ["example.com"]) is False

    def test_empty_string_origin_blocked(self):
        assert is_origin_allowed("", ["example.com"]) is False

    def test_malformed_origin_blocked(self):
        assert is_origin_allowed("not-a-url", ["example.com"]) is False

    # ── 여러 도메인 화이트리스트 ────────────────────────────────────
    def test_multiple_domains_first_matches(self):
        assert is_origin_allowed("https://a.com", ["a.com", "b.com"]) is True

    def test_multiple_domains_second_matches(self):
        assert is_origin_allowed("https://b.com", ["a.com", "b.com"]) is True

    def test_multiple_domains_none_match(self):
        assert is_origin_allowed("https://c.com", ["a.com", "b.com"]) is False
