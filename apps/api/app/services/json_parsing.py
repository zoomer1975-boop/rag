"""LLM 응답 JSON 파서 — 코드펜스/잡음 앞뒤 텍스트에 내성."""

from __future__ import annotations

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """LLM 출력에서 JSON object 를 best-effort 로 추출한다.

    시도 순서:
      1) 입력 전체
      2) 첫 ``` 펜스 내부
      3) 첫 '{' 와 마지막 '}' 사이 substring
    object 가 아니거나 파싱 실패면 None.
    """
    if not raw:
        return None

    candidates: list[str] = [raw]
    fence = _CODE_FENCE_RE.search(raw)
    if fence:
        candidates.insert(0, fence.group(1))

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None
