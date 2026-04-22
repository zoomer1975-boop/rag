"""url_guard 단위 테스트"""

import pytest

from app.services.security import url_guard
from app.services.security.types import SecurityError


def test_https_scheme_allowed():
    url_guard.validate_scheme("https://example.com/page")


def test_http_scheme_allowed():
    url_guard.validate_scheme("http://example.com/page")


def test_ftp_scheme_blocked():
    with pytest.raises(SecurityError):
        url_guard.validate_scheme("ftp://evil.com/file")


def test_file_scheme_blocked():
    with pytest.raises(SecurityError):
        url_guard.validate_scheme("file:///etc/passwd")


def test_javascript_scheme_blocked():
    with pytest.raises(SecurityError):
        url_guard.validate_scheme("javascript:alert(1)")


def test_data_scheme_blocked():
    with pytest.raises(SecurityError):
        url_guard.validate_scheme("data:text/html,<script>alert(1)</script>")
