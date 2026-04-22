"""URL 인제스트 보안 검사 — Jina Reader 사용 전 스킴 검증"""

from __future__ import annotations

from .types import SecurityError, Severity, Threat

_ALLOWED_SCHEMES = {"http", "https"}


def validate_scheme(url: str) -> None:
    """URL 스킴이 http/https인지 검증한다. 위반 시 SecurityError 발생."""
    scheme = url.split("://", 1)[0].lower().strip()
    if scheme not in _ALLOWED_SCHEMES:
        raise SecurityError(
            Threat(
                category="invalid_scheme",
                severity=Severity.HIGH,
                detail=f"허용되지 않는 URL 스킴: {scheme!r}. http 또는 https만 허용됩니다.",
                location=url[:200],
            )
        )
