"""위젯 인사말 다국어 선택 서비스

greeting은 두 가지 형태로 저장될 수 있습니다:
  - str: 단일 문자열 (기존 방식, 그대로 반환)
  - dict: {"ko": "안녕하세요!", "en": "Hello!", ...} (다국어 지원)

브라우저 Accept-Language에서 해석된 lang_code를 받아
가장 적합한 greeting 문자열을 반환합니다.
"""

from __future__ import annotations

from typing import Any


def resolve_greeting(
    greeting: Any,
    lang_code: str,
    default_lang: str = "ko",
) -> str:
    """greeting 값에서 lang_code에 맞는 인사말을 반환합니다.

    Args:
        greeting: 단일 문자열 또는 {lang: text} 딕셔너리.
        lang_code: 감지된 언어 코드 (예: "ko", "en", "zh-TW").
        default_lang: dict에서 lang_code 매칭 실패 시 차선 언어.

    Returns:
        선택된 인사말 문자열. 매칭 실패 시 첫 번째 값 반환.
    """
    if greeting is None:
        return ""

    # 단일 문자열 — 그대로 반환
    if isinstance(greeting, str):
        return greeting

    # dict 형식 처리
    if not isinstance(greeting, dict) or not greeting:
        return ""

    # 1) 정확한 매칭
    if lang_code in greeting:
        return greeting[lang_code]

    # 2) 접두어 매칭 (예: "zh-TW" → "zh")
    prefix = lang_code.split("-")[0]
    if prefix in greeting:
        return greeting[prefix]

    # 3) default_lang으로 폴백
    if default_lang in greeting:
        return greeting[default_lang]

    # 3b) default_lang prefix 매칭
    default_prefix = default_lang.split("-")[0]
    if default_prefix in greeting:
        return greeting[default_prefix]

    # 4) 첫 번째 값으로 폴백
    return next(iter(greeting.values()))
