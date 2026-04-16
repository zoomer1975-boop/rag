"""Web API Tool 실행 서비스 — SSRF 방지 포함"""

import json
import logging
import re
from typing import Any

import httpx

from app.models.tenant_api_tool import TenantApiTool
from app.services.encryption import decrypt
from app.services.ssrf_guard import SSRFError, validate_url

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 100 * 1024  # 100KB
MAX_TOOL_CALLS_PER_CHAT = 3

# path parameter placeholder 패턴: {param_name}
_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")


def build_openai_tools(tools: list[TenantApiTool]) -> list[dict]:
    """활성 TenantApiTool 목록을 OpenAI function calling `tools` 파라미터 형식으로 변환."""
    result = []
    for tool in tools:
        if not tool.is_active:
            continue

        # 파라미터 스키마 조합 (query + body)
        properties: dict[str, Any] = {}
        required: list[str] = []

        # path parameter는 항상 필수
        for path_param in _PATH_PARAM_RE.findall(tool.url_template):
            properties[path_param] = {
                "type": "string",
                "description": f"URL path parameter: {path_param}",
            }
            required.append(path_param)

        if tool.query_params_schema:
            props = tool.query_params_schema.get("properties", {})
            req = tool.query_params_schema.get("required", [])
            properties.update(props)
            required.extend(r for r in req if r not in required)

        if tool.body_schema:
            props = tool.body_schema.get("properties", {})
            req = tool.body_schema.get("required", [])
            properties.update(props)
            required.extend(r for r in req if r not in required)

        result.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })

    return result


async def execute_tool(tool: TenantApiTool, arguments: dict[str, Any]) -> str:
    """tool 설정과 LLM이 제공한 arguments로 실제 HTTP 요청을 실행한다.

    Args:
        tool: 실행할 TenantApiTool 인스턴스
        arguments: LLM이 반환한 tool call arguments dict

    Returns:
        응답 본문 문자열 (최대 MAX_RESPONSE_BYTES)

    Raises:
        SSRFError: SSRF 위험 URL
        httpx.TimeoutException: 요청 타임아웃
        Exception: 기타 HTTP 오류
    """
    # 1. URL 조합 (path parameter 치환)
    url = tool.url_template
    path_params = _PATH_PARAM_RE.findall(url)
    for param in path_params:
        value = arguments.get(param, "")
        url = url.replace(f"{{{param}}}", str(value))

    # 2. SSRF 방지 검증
    await validate_url(url)

    # 3. 헤더 복호화
    headers: dict[str, str] = {}
    if tool.headers_encrypted:
        try:
            headers = json.loads(decrypt(tool.headers_encrypted))
        except Exception:
            logger.warning("tool '%s': headers 복호화 실패, 빈 헤더로 진행", tool.name)

    # 4. query params / body 분리
    query_params: dict[str, Any] = {}
    body: dict[str, Any] | None = None

    query_schema_props = set()
    if tool.query_params_schema:
        query_schema_props = set(tool.query_params_schema.get("properties", {}).keys())

    body_schema_props = set()
    if tool.body_schema:
        body_schema_props = set(tool.body_schema.get("properties", {}).keys())

    path_param_set = set(path_params)

    for key, val in arguments.items():
        if key in path_param_set:
            continue  # 이미 URL에 삽입됨
        if key in query_schema_props:
            query_params[key] = val
        elif key in body_schema_props:
            if body is None:
                body = {}
            body[key] = val
        else:
            # 스키마에 없는 인자는 GET이면 query, 아니면 body로
            if tool.http_method == "GET":
                query_params[key] = val
            else:
                if body is None:
                    body = {}
                body[key] = val

    logger.info(
        "tool_execute: name=%s method=%s url=%s query=%s body=%s",
        tool.name, tool.http_method, url, query_params, bool(body),
    )

    # 5. HTTP 요청
    timeout = min(tool.timeout_seconds, 30)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        response = await client.request(
            method=tool.http_method,
            url=url,
            headers=headers,
            params=query_params if query_params else None,
            json=body,
        )

    # 6. 응답 처리
    raw = response.content[:MAX_RESPONSE_BYTES]
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = repr(raw)

    logger.info("tool_execute: name=%s status=%d response_len=%d", tool.name, response.status_code, len(text))

    # 7. JMESPath 추출 (설정된 경우)
    if tool.response_jmespath and text:
        try:
            import jmespath  # optional dependency
            parsed = json.loads(text)
            extracted = jmespath.search(tool.response_jmespath, parsed)
            text = json.dumps(extracted, ensure_ascii=False)
        except Exception as e:
            logger.warning("tool '%s': jmespath 추출 실패 (%s), 전체 응답 사용", tool.name, e)

    return f"[HTTP {response.status_code}]\n{text}"
