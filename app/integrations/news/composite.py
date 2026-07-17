"""Маршрутизация источников новостей к подходящему провайдеру.

middlecorridor.com — скрейпер (RSS нет), всё остальное — RSS/Atom.
Новые источники со своей логикой добавляются новым маршрутом.
"""

from app.integrations.news.base import NewsEntry, NewsProvider
from app.integrations.news.middlecorridor import MiddleCorridorScraper
from app.integrations.news.rss import RssNewsProvider


class CompositeNewsProvider:
    """NewsProvider, выбирающий реализацию по URL источника."""

    def __init__(self, rss: RssNewsProvider, scraper: MiddleCorridorScraper) -> None:
        self._rss = rss
        self._scraper = scraper

    async def fetch(self, feed_url: str) -> list[NewsEntry]:
        provider: NewsProvider = (
            self._scraper if MiddleCorridorScraper.matches(feed_url) else self._rss
        )
        return await provider.fetch(feed_url)

    async def aclose(self) -> None:
        await self._rss.aclose()
        await self._scraper.aclose()
