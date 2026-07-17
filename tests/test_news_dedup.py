"""Тесты новостной ленты: дедуп, троттлинг, архив старья, RSS-парсер (§7.3)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import NewsItem
from app.integrations.news.base import NewsEntry, NewsProviderError
from app.integrations.news.rss import RssNewsProvider
from app.services.news_feed import NewsFeedService

NOW = datetime.now(UTC)


def _entry(url: str, title: str = "Заголовок", age_days: int = 0) -> NewsEntry:
    return NewsEntry(
        source="example.com",
        url=url,
        title=title,
        published_at=NOW - timedelta(days=age_days),
    )


class FakeNewsProvider:
    def __init__(self) -> None:
        self.feeds: dict[str, list[NewsEntry]] = {}
        self.errors: dict[str, Exception] = {}

    async def fetch(self, feed_url: str) -> list[NewsEntry]:
        if feed_url in self.errors:
            raise self.errors[feed_url]
        return self.feeds.get(feed_url, [])


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.error: Exception | None = None

    async def publish(self, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(text)


@pytest.fixture
def provider() -> FakeNewsProvider:
    return FakeNewsProvider()


@pytest.fixture
def sink() -> FakeSink:
    return FakeSink()


def _service(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    sources: list[str] | None = None,
    max_per_run: int = 3,
) -> NewsFeedService:
    return NewsFeedService(
        session_factory,
        provider,
        sources=sources or ["https://example.com/feed"],
        sink=sink,
        max_per_run=max_per_run,
        max_age_days=7,
    )


async def _all_items(session: AsyncSession) -> list[NewsItem]:
    return list((await session.execute(select(NewsItem).order_by(NewsItem.id))).scalars())


async def test_dedup_across_runs(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.feeds["https://example.com/feed"] = [_entry("https://e/1"), _entry("https://e/2")]
    service = _service(session_factory, provider, sink)

    assert await service.fetch_and_store() == 2
    assert await service.fetch_and_store() == 0  # повторный прогон — дубликатов нет

    assert len(await _all_items(session)) == 2


async def test_dedup_within_batch(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.feeds["https://example.com/feed"] = [
        _entry("https://e/1", "Первая"),
        _entry("https://e/1", "Дубль в той же ленте"),
    ]
    service = _service(session_factory, provider, sink)
    assert await service.fetch_and_store() == 1
    assert len(await _all_items(session)) == 1


async def test_old_items_archived_without_publishing(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.feeds["https://example.com/feed"] = [
        _entry("https://e/fresh", age_days=1),
        _entry("https://e/old", age_days=30),
    ]
    service = _service(session_factory, provider, sink)
    await service.fetch_and_store()
    await service.publish_pending()

    items = {item.url: item for item in await _all_items(session)}
    assert items["https://e/old"].is_sent is True  # архив
    assert items["https://e/fresh"].is_sent is True  # опубликована
    assert len(sink.messages) == 1
    assert "fresh" in sink.messages[0]


async def test_publish_throttled_per_run(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.feeds["https://example.com/feed"] = [_entry(f"https://e/{i}") for i in range(5)]
    service = _service(session_factory, provider, sink, max_per_run=3)
    await service.fetch_and_store()

    assert await service.publish_pending() == 3  # троттлинг
    assert await service.publish_pending() == 2  # добор в следующий прогон
    assert await service.publish_pending() == 0
    assert len(sink.messages) == 5


async def test_source_failure_does_not_crash_run(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.errors["https://bad.example/feed"] = NewsProviderError("недоступен")
    provider.feeds["https://example.com/feed"] = [_entry("https://e/1")]
    service = _service(
        session_factory,
        provider,
        sink,
        sources=["https://bad.example/feed", "https://example.com/feed"],
    )
    assert await service.fetch_and_store() == 1


async def test_publish_failure_keeps_items_pending(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeNewsProvider,
    sink: FakeSink,
    session: AsyncSession,
) -> None:
    provider.feeds["https://example.com/feed"] = [_entry("https://e/1")]
    service = _service(session_factory, provider, sink)
    await service.fetch_and_store()

    sink.error = RuntimeError("telegram down")
    assert await service.publish_pending() == 0

    items = await _all_items(session)
    assert items[0].is_sent is False  # уйдёт в следующий прогон


# --- RSS-парсер -----------------------------------------------------------------

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example Corridor News</title>
  <item>
    <title>TITR sets cargo record</title>
    <link>https://example.com/titr-record</link>
    <guid>post-101</guid>
    <description>&lt;p&gt;Volumes &lt;b&gt;doubled&lt;/b&gt; this year.&lt;/p&gt;</description>
    <pubDate>Thu, 16 Jul 2026 10:00:00 +0000</pubDate>
  </item>
  <item>
    <title>No link item is skipped</title>
  </item>
</channel></rss>
"""


async def test_rss_provider_parses_feed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SAMPLE_FEED)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = RssNewsProvider(client=client)
    entries = await provider.fetch("https://www.example.com/feed/")

    assert len(entries) == 1  # элемент без ссылки пропущен
    entry = entries[0]
    assert entry.source == "example.com"  # www. срезан
    assert entry.title == "TITR sets cargo record"
    assert entry.url == "https://example.com/titr-record"
    assert entry.external_id == "post-101"
    assert entry.summary == "Volumes doubled this year."  # HTML вычищен
    assert entry.published_at == datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    await client.aclose()


async def test_rss_provider_error_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = RssNewsProvider(client=client)
    with pytest.raises(NewsProviderError):
        await provider.fetch("https://example.com/feed")
    await client.aclose()
