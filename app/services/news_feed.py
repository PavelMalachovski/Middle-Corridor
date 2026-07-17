"""Новостная лента коридора (§7.3): сбор, дедуп, перевод, публикация.

Дедуп по URL — и внутри батча, и против БД (плюс unique-констрейнт как
последний рубеж). Свежие новости встают в очередь публикации; новости старше
NEWS_MAX_AGE_DAYS сохраняются сразу как «отправленные» (архив) — чтобы первый
запуск на живых лентах не завалил канал старьём. Англоязычные новости перед
публикацией переводятся LLM (если переводчик сконфигурирован); сбой перевода
не блокирует публикацию — уходит оригинал.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import NewsItem
from app.db.repositories.news import NewsRepository
from app.integrations.news.base import NewsProvider
from app.services.formatting import format_news_item
from app.services.sinks import MessageSink

logger = structlog.get_logger(__name__)

_CYRILLIC = re.compile("[а-яА-ЯёЁ]")


class NewsTranslator(Protocol):
    async def translate(self, title: str, summary: str | None) -> tuple[str, str | None]: ...


def needs_translation(item: NewsItem) -> bool:
    """Переводим только то, что ещё не переведено и не на русском."""
    return item.title_ru is None and not _CYRILLIC.search(item.title)


@dataclass(frozen=True, slots=True)
class NewsRunStats:
    stored: int
    published: int


class NewsFeedService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: NewsProvider,
        sources: list[str],
        sink: MessageSink | None = None,
        max_per_run: int = 3,
        max_age_days: int = 7,
        translator: NewsTranslator | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._sources = sources
        self._sink = sink
        self._max_per_run = max_per_run
        self._max_age = timedelta(days=max_age_days)
        self._translator = translator

    async def fetch_and_store(self) -> int:
        """Собирает все источники, сохраняет новые элементы. Возвращает число новых."""
        cutoff = datetime.now(UTC) - self._max_age
        stored = 0
        async with self._session_factory() as session:
            repo = NewsRepository(session)
            for source_url in self._sources:
                try:
                    entries = await self._provider.fetch(source_url)
                except Exception as exc:  # noqa: BLE001 — один источник не роняет прогон
                    logger.error("news_source_failed", source=source_url, error=str(exc))
                    continue

                seen = await repo.existing_urls(entry.url for entry in entries)
                for entry in entries:
                    if entry.url in seen:
                        continue
                    seen.add(entry.url)  # дедуп внутри батча
                    is_archive = entry.published_at is not None and entry.published_at < cutoff
                    await repo.add(entry, is_sent=is_archive)
                    stored += 1
                logger.info("news_source_fetched", source=source_url, entries=len(entries))
            await session.commit()
        logger.info("news_stored", new_items=stored)
        return stored

    async def publish_pending(self) -> int:
        """Публикует не более max_per_run новостей за прогон (троттлинг)."""
        if self._sink is None:
            return 0
        sent = 0
        async with self._session_factory() as session:
            repo = NewsRepository(session)
            for item in await repo.list_unsent(limit=self._max_per_run):
                await self._maybe_translate(item)
                try:
                    await self._sink.publish(format_news_item(item))
                except Exception as exc:  # noqa: BLE001
                    # канал недоступен — оставшиеся уйдут в следующий прогон
                    logger.error("news_publish_failed", item_id=item.id, error=str(exc))
                    break
                item.is_sent = True
                sent += 1
            await session.commit()
        if sent:
            logger.info("news_published", count=sent)
        return sent

    async def _maybe_translate(self, item: NewsItem) -> None:
        """Переводит item на месте; сбой перевода не блокирует публикацию."""
        if self._translator is None or not needs_translation(item):
            return
        try:
            item.title_ru, item.summary_ru = await self._translator.translate(
                item.title, item.summary
            )
        except Exception as exc:  # noqa: BLE001 — публикуем оригинал
            logger.warning("news_translation_failed", item_id=item.id, error=str(exc))

    async def run_once(self) -> "NewsRunStats":
        """Полный цикл джобы: сбор + публикация."""
        stored = await self.fetch_and_store()
        published = await self.publish_pending()
        return NewsRunStats(stored=stored, published=published)
