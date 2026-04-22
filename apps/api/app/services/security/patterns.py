"""프롬프트 인젝션 및 악성 콘텐츠 탐지 패턴"""

from __future__ import annotations

import re

# ── 프롬프트 인젝션 패턴 ────────────────────────────────────────────────────
# 한국어 + 영어 공격 패턴
_PROMPT_INJECTION_PHRASES = [
    # 역할 전환 / 지시 무시
    r"이전\s*지시(?:사항)?\s*(?:를|을)\s*무시",
    r"(?:모든|앞의|위의|이전)\s*(?:지시|명령|규칙)\s*(?:를|을|은|는)\s*(?:무시|잊어버려|삭제)",
    r"새로운\s*(?:지시|역할|규칙)\s*(?:를|을)\s*따르",
    r"(?:시스템|system)\s*프롬프트\s*(?:를|을)\s*(?:무시|공개|출력|알려)",
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|your)\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above|your)\s+instructions?",
    r"forget\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|context|rules?)",
    r"new\s+(?:instructions?|directives?|rules?)\s*:",
    r"you\s+are\s+now\s+(?:a|an|DAN|jailbreak)",
    r"act\s+as\s+(?:a|an|if)\s+(?:you\s+(?:are|were)\s+)?(?:a|an|DAN|evil|unrestricted)",
    r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a|an\s+)?(?:evil|malicious|unrestricted)",
    r"(?:do\s+)?anything\s+now",  # DAN variant
    r"jailbreak",
    r"prompt\s*injection",
    r"override\s+(?:the\s+)?(?:system\s+)?(?:prompt|instructions?|rules?)",
    r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
    r"repeat\s+(?:the\s+)?(?:system\s+)?prompt",
    # 역할 전환
    r"(?:you\s+are|you're)\s+(?:now\s+)?(?:a|an)\s+(?:helpful\s+)?(?:AI|assistant)\s+(?:that|who)\s+(?:can|will)\s+(?:do|provide|help|assist).*?(?:anything|everything|any|all)",
]

PROMPT_INJECTION_RE = re.compile(
    "|".join(f"(?:{p})" for p in _PROMPT_INJECTION_PHRASES),
    re.IGNORECASE | re.UNICODE,
)

# ── 스크립트/HTML 인젝션 패턴 ────────────────────────────────────────────────
SCRIPT_TAG_RE = re.compile(
    r"<\s*script[\s>].*?(?:</\s*script\s*>|$)",
    re.IGNORECASE | re.DOTALL,
)

JAVASCRIPT_PROTO_RE = re.compile(
    r"javascript\s*:",
    re.IGNORECASE,
)

INLINE_EVENT_RE = re.compile(
    r"\bon\w+\s*=\s*['\"]",
    re.IGNORECASE,
)

DATA_URI_SCRIPT_RE = re.compile(
    r"data\s*:\s*text/(?:html|javascript)",
    re.IGNORECASE,
)

# ── 유니코드 비가시 문자 ──────────────────────────────────────────────────────
# 유니코드 태그 블록 (U+E0000–U+E007F) - 숨겨진 텍스트 인젝션에 사용
UNICODE_TAG_RE = re.compile(r"[\U000E0000-\U000E007F]+")

# 기타 비가시 제어 문자 (줄바꿈/탭 제외)
INVISIBLE_CHARS_RE = re.compile(
    r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff]+"
)

# ── 이상 토큰 탐지 ────────────────────────────────────────────────────────────
# 2000자 이상의 연속된 비공백 문자열 (바이너리/인코딩 페이로드 의심)
ANOMALOUS_TOKEN_RE = re.compile(r"\S{2000,}")

# base64 블록 탐지 (80자 이상 연속 base64 문자)
BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")

# ── PDF 위험 키워드 (바이트 스캔용) ──────────────────────────────────────────
PDF_DANGEROUS_KEYWORDS: list[bytes] = [
    b"/JS",
    b"/JavaScript",
    b"/Launch",
    b"/OpenAction",
    b"/AA",          # Additional Actions
    b"/EmbeddedFile",
    b"/RichMedia",
    b"/XFA",
]
