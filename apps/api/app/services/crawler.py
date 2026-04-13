"""웹 크롤러 — Jina Reader API 기반 HTML→Markdown 변환"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

JINA_READER_BASE = "https://r.jina.ai/"


class WebCrawler:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    async def crawl_url(self, url: str) -> dict:
        """Jina Reader를 이용해 URL을 Markdown으로 변환하여 반환합니다."""
        jina_url = f"{JINA_READER_BASE}{url}"
        headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
        if settings.jina_api_key:
            headers["Authorization"] = f"Bearer {settings.jina_api_key}"

        timeout = httpx.Timeout(connect=10.0, read=self.timeout, write=10.0, pool=5.0)
        logger.info("Jina Reader 요청: %s", jina_url)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(jina_url, headers=headers, follow_redirects=True)
            response.raise_for_status()
        logger.info("Jina Reader 응답: %d, 길이=%d", response.status_code, len(response.text))

        content = response.text.strip()
        title = self._extract_title(content) or url
        return {"url": url, "title": title, "content": content}

    async def crawl_site(self, start_url: str) -> list[dict]:
        """단일 URL을 인제스트합니다.

        Jina Reader는 단일 URL 변환만 지원하므로 start_url 하나만 처리합니다.
        """
        page = await self.crawl_url(start_url)
        return [page]

    def _extract_title(self, markdown: str) -> str:
        """마크다운 첫 번째 # 헤딩을 제목으로 추출합니다."""
        for line in markdown.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return ""
