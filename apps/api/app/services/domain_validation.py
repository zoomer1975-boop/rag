"""도메인 화이트리스트 검증 서비스"""

from urllib.parse import urlparse


def is_origin_allowed(origin: str | None, allowed_domains: list[str]) -> bool:
    """Origin 헤더가 허용된 도메인 목록에 포함되는지 확인.

    Args:
        origin: 브라우저가 전송한 Origin 헤더 값 (예: "https://example.com:8443")
        allowed_domains: 허용된 도메인 목록 (예: ["example.com", "localhost"])

    Returns:
        True — 허용, False — 차단

    Notes:
        - 빈 allowed_domains 목록은 모든 Origin 허용 (개발 환경 호환)
        - 포트는 무시하고 호스트명만 비교
        - None 또는 빈 문자열 Origin은 화이트리스트가 있으면 차단
    """
    if not allowed_domains:
        return True

    if not origin:
        return False

    try:
        parsed = urlparse(origin)
        # urlparse 가 scheme 없는 URL 을 path 로 파싱하므로 scheme 필수 체크
        if not parsed.scheme or not parsed.hostname:
            return False
        host = parsed.hostname  # 포트 제거된 순수 호스트명
    except Exception:
        return False

    return host in allowed_domains
