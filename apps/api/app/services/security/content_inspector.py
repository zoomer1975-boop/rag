"""텍스트 콘텐츠 보안 검사 — 프롬프트 인젝션, 스크립트, 이상 토큰 탐지"""

from __future__ import annotations

import logging
import unicodedata

from .patterns import (
    ANOMALOUS_TOKEN_RE,
    BASE64_BLOB_RE,
    INVISIBLE_CHARS_RE,
    JAVASCRIPT_PROTO_RE,
    PROMPT_INJECTION_RE,
    SCRIPT_TAG_RE,
    UNICODE_TAG_RE,
)
from .types import Action, Severity, Threat, ThreatReport

logger = logging.getLogger(__name__)

# 단일 청크/문서에서 허용하는 이상 토큰 최대 개수
_MAX_ANOMALOUS_TOKENS = 3
# base64 블롭 최대 허용 개수
_MAX_BASE64_BLOBS = 5


def inspect(text: str, source_type: str = "unknown") -> ThreatReport:
    """텍스트를 검사하고 ThreatReport를 반환한다.

    - source_type: "url" | "pdf" | "docx" | "txt" | "md" | "unknown"
    """
    report = ThreatReport()
    working = _normalize(text)

    # 1. 스크립트 / HTML 인젝션 (URL 크롤 결과에서도 잔존 가능)
    working, script_threats = _strip_scripts(working)
    report.threats.extend(script_threats)

    # 2. 프롬프트 인젝션
    injection_threats = _detect_prompt_injection(working)
    report.threats.extend(injection_threats)

    # 3. 이상 토큰 (바이너리/인코딩 페이로드)
    anomaly_threats = _detect_anomalous_tokens(working)
    report.threats.extend(anomaly_threats)

    if not report.threats:
        return report

    worst = report.worst_severity
    if worst in (Severity.CRITICAL, Severity.HIGH):
        report.action = Action.BLOCK
    else:
        report.action = Action.SANITIZE
        report.sanitized_text = working

    _log_threats(report, source_type)
    return report


def _normalize(text: str) -> str:
    """NFKC 정규화 + 비가시 문자 제거"""
    text = unicodedata.normalize("NFKC", text)
    text = UNICODE_TAG_RE.sub("", text)
    text = INVISIBLE_CHARS_RE.sub("", text)
    return text


def _strip_scripts(text: str) -> tuple[str, list[Threat]]:
    threats: list[Threat] = []
    matches = SCRIPT_TAG_RE.findall(text)
    if matches:
        threats.append(
            Threat(
                category="script_injection",
                severity=Severity.MEDIUM,
                detail=f"<script> 태그 {len(matches)}개 탐지. 제거됩니다.",
            )
        )
        text = SCRIPT_TAG_RE.sub("", text)

    if JAVASCRIPT_PROTO_RE.search(text):
        threats.append(
            Threat(
                category="script_injection",
                severity=Severity.MEDIUM,
                detail="javascript: 프로토콜 탐지. 제거됩니다.",
            )
        )
        text = JAVASCRIPT_PROTO_RE.sub("[removed]", text)

    return text, threats


def _detect_prompt_injection(text: str) -> list[Threat]:
    matches = PROMPT_INJECTION_RE.findall(text)
    if not matches:
        return []

    # 매칭된 패턴 중 최대 3개만 로그 (민감 정보 최소화)
    samples = [m[:100] if isinstance(m, str) else str(m)[:100] for m in matches[:3]]
    return [
        Threat(
            category="prompt_injection",
            severity=Severity.HIGH,
            detail=f"프롬프트 인젝션 패턴 {len(matches)}건 탐지: {samples}",
        )
    ]


def _detect_anomalous_tokens(text: str) -> list[Threat]:
    threats: list[Threat] = []

    long_tokens = ANOMALOUS_TOKEN_RE.findall(text)
    if len(long_tokens) > _MAX_ANOMALOUS_TOKENS:
        threats.append(
            Threat(
                category="anomalous_token",
                severity=Severity.MEDIUM,
                detail=f"비정상적으로 긴 토큰 {len(long_tokens)}개 탐지 (각 2000자 이상).",
            )
        )

    base64_blobs = BASE64_BLOB_RE.findall(text)
    if len(base64_blobs) > _MAX_BASE64_BLOBS:
        threats.append(
            Threat(
                category="encoded_payload",
                severity=Severity.MEDIUM,
                detail=f"base64 인코딩 블롭 {len(base64_blobs)}개 탐지. 페이로드 은닉 의심.",
            )
        )

    return threats


def _log_threats(report: ThreatReport, source_type: str) -> None:
    for threat in report.threats:
        logger.warning(
            "보안 위협 탐지 | source=%s category=%s severity=%s detail=%s",
            source_type,
            threat.category,
            threat.severity,
            threat.truncated_detail(),
        )
