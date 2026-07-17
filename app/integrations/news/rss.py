"""RSS/Atom-провайдер новостей.

httpx забирает ленту (ретраи с backoff), feedparser разбирает её в отдельном
треде (он синхронный), selectolax вычищает HTML из описаний.
"""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser
import httpx
import structlog
from selectolax.parser import HTMLParser

from app.integrations.news.base import NewsEntry, NewsProviderError

logger = structlog.get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _strip_html(text: str) -> str:
    return HTMLParser(text).text(separator=" ", strip=True)


def _source_name(feed_url: str) -> str:
    host = urlparse(feed_url).netloc
    return host.removeprefix("www.")


class RssNewsProvider:
    """Реализация NewsProvider для RSS/Atom-лент."""

    def __init__(self, client: httpx.AsyncClient | None = None, retries: int = 3) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "mc-status/0.1 (+middle corridor news digest)"},
        )
        self._retries = retries

    async def fetch(self, feed_url: str) -> list[NewsEntry]:
        content = await self._get(feed_url)
        parsed = await asyncio.to_thread(feedparser.parse, content)
        if parsed.get("bozo") and not parsed.entries:
            raise NewsProviderError(f"Лента не распарсилась: {feed_url}")

        source = _source_name(feed_url)
        entries: list[NewsEntry] = []
        for entry in parsed.entries:
            url = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not url or not title:
                continue
            summary_raw = entry.get("summary") or entry.get("description") or ""
            summary = _strip_html(summary_raw).strip() or None
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            published_at = datetime(*published[:6], tzinfo=UTC) if published is not None else None
            entries.append(
                NewsEntry(
                    source=source,
                    url=url,
                    title=title,
                    external_id=(entry.get("id") or None),
                    summary=summary,
                    published_at=published_at,
                )
            )
        return entries

    async def _get(self, feed_url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            if attempt:
                await asyncio.sleep(min(2**attempt, 8))
            try:
                response = await self._client.get(feed_url)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("news_fetch_failed", url=feed_url, attempt=attempt, error=str(exc))
                continue
            if response.status_code in _RETRYABLE_STATUS:
                last_error = NewsProviderError(f"HTTP {response.status_code}")
                continue
            if response.status_code != 200:
                raise NewsProviderError(f"HTTP {response.status_code}: {feed_url}")
            return response.content
        raise NewsProviderError(f"Источник недоступен: {feed_url}") from last_error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
