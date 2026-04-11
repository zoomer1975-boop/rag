"""브라우저 언어 감지 및 LLM 프롬프트 주입 서비스"""

LANG_INSTRUCTIONS: dict[str, str] = {
    "ko": "반드시 한국어(Korean)로 답변하세요.",
    "en": "You must respond in English.",
    "ja": "必ず日本語で回答してください。",
    "zh": "请务必用中文回答。",
    "es": "Debes responder en español.",
    "fr": "Vous devez répondre en français.",
    "de": "Sie müssen auf Deutsch antworten.",
    "pt": "Você deve responder em português.",
    "vi": "Bạn phải trả lời bằng tiếng Việt.",
    "th": "คุณต้องตอบเป็นภาษาไทย",
}

KNOWN_LANGUAGES = set(LANG_INSTRUCTIONS.keys())


class LanguageService:
    def __init__(self, default_language: str = "ko") -> None:
        self.default_language = default_language

    def parse_accept_language(self, header: str | None) -> str:
        """Accept-Language 헤더에서 기본 언어 코드를 추출합니다.

        Examples:
            "ko-KR,ko;q=0.9,en-US;q=0.8" → "ko"
            "en-US" → "en"
            "" / None → default_language
        """
        if not header:
            return self.default_language

        # 콤마로 분리 후 quality value 기준 정렬 (이미 내림차순이 대부분이지만 명시적으로)
        parts = [p.strip() for p in header.split(",")]

        candidates: list[tuple[float, str]] = []
        for part in parts:
            segments = part.split(";")
            lang_tag = segments[0].strip()
            quality = 1.0
            for seg in segments[1:]:
                seg = seg.strip()
                if seg.startswith("q="):
                    try:
                        quality = float(seg[2:])
                    except ValueError:
                        pass

            base_lang = lang_tag.split("-")[0].lower()
            candidates.append((quality, base_lang))

        # 품질값 내림차순 정렬
        candidates.sort(key=lambda x: x[0], reverse=True)

        for _, lang in candidates:
            if lang in KNOWN_LANGUAGES:
                return lang

        return self.default_language

    def resolve_lang(
        self,
        detected: str,
        policy: str,
        default_lang: str,
        allowed_langs: list[str],
    ) -> str:
        """테넌트 언어 정책을 적용해 최종 언어 코드를 반환합니다.

        Args:
            detected: 브라우저에서 감지된 언어 코드
            policy: "auto" | "fixed" | "whitelist"
            default_lang: 테넌트 기본 언어
            allowed_langs: whitelist 정책의 허용 목록
        """
        if policy == "fixed":
            return default_lang

        if policy == "whitelist":
            return detected if detected in allowed_langs else default_lang

        # auto
        return detected if detected in KNOWN_LANGUAGES else default_lang

    def build_lang_instruction(self, lang_code: str) -> str:
        """LLM 시스템 프롬프트에 삽입할 언어 지시문을 반환합니다."""
        return LANG_INSTRUCTIONS.get(
            lang_code,
            f"You must respond in the language with code '{lang_code}'. "
            "If unsure, respond in the same language the user is using.",
        )
