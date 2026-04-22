"""보안 필터링 공통 타입"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Action(str, Enum):
    ALLOW = "allow"
    SANITIZE = "sanitize"
    BLOCK = "block"


@dataclass(frozen=True)
class Threat:
    category: str
    severity: Severity
    detail: str
    location: str = ""

    def truncated_detail(self, max_len: int = 200) -> str:
        return self.detail[:max_len] + "..." if len(self.detail) > max_len else self.detail


@dataclass
class ThreatReport:
    threats: list[Threat] = field(default_factory=list)
    action: Action = Action.ALLOW
    sanitized_text: str | None = None

    @property
    def has_threats(self) -> bool:
        return bool(self.threats)

    @property
    def worst_severity(self) -> Severity | None:
        if not self.threats:
            return None
        order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        for sev in order:
            if any(t.severity == sev for t in self.threats):
                return sev
        return None


class SecurityError(Exception):
    """파일/URL이 보안 정책에 의해 차단될 때 발생"""

    def __init__(self, threat: Threat) -> None:
        self.threat = threat
        super().__init__(f"[{threat.category}] {threat.detail}")
