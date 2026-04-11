"""웹 크롤러 — Playwright 기반 JavaScript 렌더링 지원"""

import asyncio
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


class WebCrawler:
    def __init__(self, max_pages: int = 20, delay_ms: int = 500) -> None:
        self.max_pages = max_pages
        self.delay_ms = delay_ms

    async def crawl_url(self, url: str) -> dict:
        """단일 URL을 크롤링하여 텍스트와 메타데이터를 반환합니다."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                title = await page.title()
            finally:
                await browser.close()

        text = self._extract_text(html)
        return {"url": url, "title": title, "content": text}

    async def crawl_site(self, start_url: str) -> list[dict]:
        """사이트 전체를 크롤링합니다 (같은 도메인, max_pages 제한)."""
        base_domain = urlparse(start_url).netloc
        visited: set[str] = set()
        queue: list[str] = [start_url]
        results: list[dict] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                while queue and len(visited) < self.max_pages:
                    url = queue.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)

                    try:
                        page = await browser.new_page()
                        await page.goto(url, wait_until="networkidle", timeout=30000)
                        html = await page.content()
                        title = await page.title()
                        await page.close()
                    except Exception:
                        continue

                    text = self._extract_text(html)
                    if text:
                        results.append({"url": url, "title": title, "content": text})

                    # 같은 도메인의 링크 수집
                    links = self._extract_links(html, url, base_domain)
                    for link in links:
                        if link not in visited:
                            queue.append(link)

                    await asyncio.sleep(self.delay_ms / 1000)
            finally:
                await browser.close()

        return results

    def _extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _extract_links(self, html: str, base_url: str, domain: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc == domain and parsed.scheme in ("http", "https"):
                # fragment 제거
                clean_url = full_url.split("#")[0]
                links.append(clean_url)
        return links
