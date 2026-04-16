"""SSRF(Server-Side Request Forgery) 방지 — 외부 API 호출 전 URL 검증"""

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(ValueError):
    """SSRF 위반 시 발생하는 예외"""


# 허용되지 않는 IP 대역 (private/loopback/link-local 등)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("100.64.0.0/10"),   # shared address space
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        return True  # 파싱 실패 시 차단


async def validate_url(url: str) -> None:
    """URL이 SSRF 안전 요건을 충족하는지 검증한다.

    다음 경우에 SSRFError를 발생시킨다:
    - http/https 외 스킴
    - private/loopback/link-local IP로 resolve되는 hostname
    - hostname 없는 URL
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"허용되지 않는 URL 스킴입니다: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL에 hostname이 없습니다.")

    # DNS resolve 후 IP 검증
    try:
        # getaddrinfo는 IPv4/IPv6 모두 처리
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFError(f"hostname 해석 실패: {hostname!r} — {e}") from e

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            raise SSRFError(
                f"내부 IP로 resolve되는 hostname은 허용되지 않습니다: {hostname!r} → {ip}"
            )
