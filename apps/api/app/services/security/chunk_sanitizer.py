"""청크별 최종 프롬프트 인젝션 스위핑"""

from __future__ import annotations

import logging
import unicodedata

from .patterns import INVISIBLE_CHARS_RE, PROMPT_INJECTION_RE, UNICODE_TAG_RE
from .types import Severity, Threat, ThreatReport

logger = logging.getLogger(__name__)


def sanitize(chunk_text: str, chunk_index: int = 0) -> tuple[str, ThreatReport]:
    """청크 텍스트를 정제하고 (정제된 텍스트, ThreatReport)를 반환한다."""
    report = ThreatReport()

    text = unicodedata.normalize("NFKC", chunk_text)
    text = UNICODE_TAG_RE.sub("", text)
    text = INVISIBLE_CHARS_RE.sub("", text)

    matches = PROMPT_INJECTION_RE.findall(text)
    if matches:
        threat = Threat(
            category="prompt_injection",
            severity=Severity.HIGH,
            detail=f"청크 {chunk_index}에서 프롬프트 인젝션 패턴 {len(matches)}건 탐지.",
            location=f"chunk[{chunk_index}]",
        )
        report.threats.append(threat)
        logger.warning(
            "청크 보안 위협 | chunk=%d category=%s detail=%s",
            chunk_index,
            threat.category,
            threat.truncated_detail(),
        )

    return text, report
