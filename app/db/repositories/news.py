"""Доступ к данным новостного модуля."""

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsItem
from app.integrations.news.base import NewsEntry


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def existing_urls(self, urls: Iterable[str]) -> set[str]:
        urls = list(urls)
        if not urls:
            return set()
        result = await self._session.execute(select(NewsItem.url).where(NewsItem.url.in_(urls)))
        return set(result.scalars().all())

    async def add(self, entry: NewsEntry, is_sent: bool = False) -> NewsItem:
        item = NewsItem(
            source=entry.source,
            url=entry.url,
            external_id=entry.external_id,
            title=entry.title[:512],
            summary=entry.summary,
            published_at=entry.published_at,
            is_sent=is_sent,
        )
        self._session.add(item)
        return item

    async def list_unsent(self, limit: int) -> Sequence[NewsItem]:
        result = await self._session.execute(
            select(NewsItem).where(NewsItem.is_sent.is_(False)).order_by(NewsItem.id).limit(limit)
        )
        return result.scalars().all()
