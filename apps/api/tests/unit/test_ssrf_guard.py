"""SSRF 방지 모듈 단위 테스트"""

import pytest
from unittest.mock import patch

from app.services.ssrf_guard import SSRFError, validate_url


@pytest.mark.asyncio
async def test_valid_public_url():
    """공개 외부 URL은 통과해야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("8.8.8.8", 443))]
        await validate_url("https://api.example.com/v1/data")


@pytest.mark.asyncio
async def test_http_scheme_allowed():
    """http:// 스킴도 허용된다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("203.0.113.1", 80))]
        await validate_url("http://api.example.com/data")


@pytest.mark.asyncio
async def test_invalid_scheme_ftp():
    """ftp:// 스킴은 차단되어야 한다."""
    with pytest.raises(SSRFError, match="허용되지 않는 URL 스킴"):
        await validate_url("ftp://evil.com/file")


@pytest.mark.asyncio
async def test_invalid_scheme_file():
    """file:// 스킴은 차단되어야 한다."""
    with pytest.raises(SSRFError, match="허용되지 않는 URL 스킴"):
        await validate_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_loopback_ipv4_blocked():
    """127.x.x.x는 차단되어야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://localhost/api")


@pytest.mark.asyncio
async def test_private_10_network_blocked():
    """10.0.0.0/8 대역은 차단되어야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("10.0.0.1", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://internal.corp/api")


@pytest.mark.asyncio
async def test_private_172_network_blocked():
    """172.16.0.0/12 대역은 차단되어야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("172.16.0.1", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://internal.corp/api")


@pytest.mark.asyncio
async def test_private_192_168_network_blocked():
    """192.168.0.0/16 대역은 차단되어야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("192.168.1.100", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://router.local/api")


@pytest.mark.asyncio
async def test_link_local_blocked():
    """169.254.x.x (link-local) 대역은 차단되어야 한다 (AWS metadata 등)."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("169.254.169.254", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_ipv6_loopback_blocked():
    """::1 (IPv6 loopback)은 차단되어야 한다."""
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(None, None, None, None, ("::1", 80))]
        with pytest.raises(SSRFError, match="내부 IP"):
            await validate_url("http://localhost6/api")


@pytest.mark.asyncio
async def test_dns_failure_blocked():
    """DNS 해석 실패 시 차단되어야 한다."""
    import socket
    with patch("app.services.ssrf_guard.socket.getaddrinfo") as mock_dns:
        mock_dns.side_effect = socket.gaierror("Name or service not known")
        with pytest.raises(SSRFError, match="hostname 해석 실패"):
            await validate_url("https://nonexistent.invalid/api")


@pytest.mark.asyncio
async def test_missing_hostname_blocked():
    """hostname이 없는 URL은 차단되어야 한다."""
    with pytest.raises(SSRFError, match="hostname이 없습니다"):
        await validate_url("https:///no-host")
