"""Скрейпер новостей официального портала TITR (middlecorridor.com).

RSS у сайта нет. Русская лента /ru/press-tsentr/novosti отдаёт карточки-ссылки
вида /ru/press-tsentr/novosti/ДД-ММ-ГГГГ с заголовком в h2/h3 внутри ссылки.
Селекторы щадящие: любые <a> со ссылкой «глубже» листинга; дата — из слага.
"""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from selectolax.parser import HTMLParser

from app.integrations.news.base import NewsEntry, NewsProviderError

logger = structlog.get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SOURCE_NAME = "middlecorridor.com"


def _slug_date(slug: str) -> datetime | None:
    """Слаг статьи — дата ДД-ММ-ГГГГ."""
    try:
        return datetime.strptime(slug, "%d-%m-%Y").replace(tzinfo=UTC)
    except ValueError:
        return None


class MiddleCorridorScraper:
    """Реализация NewsProvider для листинга новостей middlecorridor.com."""

    def __init__(self, client: httpx.AsyncClient | None = None, retries: int = 3) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "mc-status/0.1 (+middle corridor news digest)"},
        )
        self._retries = retries

    @staticmethod
    def matches(url: str) -> bool:
        return "middlecorridor.com" in urlparse(url).netloc

    async def fetch(self, listing_url: str) -> list[NewsEntry]:
        html = await self._get(listing_url)
        tree = HTMLParser(html)
        listing_path = urlparse(listing_url).path.rstrip("/")

        entries: list[NewsEntry] = []
        seen: set[str] = set()
        for anchor in tree.css("a"):
            href = (anchor.attributes.get("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(listing_url, href).split("?")[0].rstrip("/")
            path = urlparse(full_url).path
            # интересны только ссылки «внутрь» листинга: /novosti/<slug>
            if not path.startswith(listing_path + "/") or full_url in seen:
                continue
            slug = path.rsplit("/", 1)[-1]
            if not slug:
                continue

            title = ""
            for heading in anchor.css("h1, h2, h3, h4"):
                title = heading.text(separator=" ", strip=True)
                if title:
                    break
            if not title:
                title = anchor.text(separator=" ", strip=True)
            if not title:
                continue

            seen.add(full_url)
            entries.append(
                NewsEntry(
                    source=SOURCE_NAME,
                    url=full_url,
                    title=title[:512],
                    external_id=slug,
                    published_at=_slug_date(slug),
                )
            )

        if not entries:
            logger.warning("middlecorridor_no_entries", url=listing_url)
        return entries

    async def _get(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            if attempt:
                await asyncio.sleep(min(2**attempt, 8))
            try:
                response = await self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = exc
                continue
            if response.status_code in _RETRYABLE_STATUS:
                last_error = NewsProviderError(f"HTTP {response.status_code}")
                continue
            if response.status_code != 200:
                raise NewsProviderError(f"HTTP {response.status_code}: {url}")
            return response.content
        raise NewsProviderError(f"Источник недоступен: {url}") from last_error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
