"""Тесты фича-пакета 2: скрейпер middlecorridor, перевод новостей, Telegram-вебхук."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.api.routes import telegram as telegram_routes
from app.config import Settings
from app.db.models import NewsItem
from app.integrations.news.base import NewsEntry
from app.integrations.news.middlecorridor import MiddleCorridorScraper
from app.services.formatting import format_news_item
from app.services.news_feed import NewsFeedService, needs_translation

# --- Скрейпер middlecorridor.com -------------------------------------------------

LISTING_HTML = """
<html><body>
  <nav><a href="/ru/press-tsentr/style">Style</a></nav>
  <div class="news-list">
    <a href="/ru/press-tsentr/novosti/26-06-2026">
      <img src="/img/1.jpg"/>
      <span>26.06.2026</span>
      <h3>TITR на Transport Logistic Shanghai 2026</h3>
    </a>
    <a href="https://middlecorridor.com/ru/press-tsentr/novosti/04-06-2026">
      <h3>Новое партнёрство ассоциации</h3>
    </a>
    <a href="/ru/press-tsentr/novosti/26-06-2026"><h3>Дубликат той же новости</h3></a>
    <a href="/ru/press-tsentr/novosti?start=6">2</a>
  </div>
</body></html>
""".encode()


async def test_middlecorridor_scraper_parses_listing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=LISTING_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = MiddleCorridorScraper(client=client)
    entries = await scraper.fetch("https://middlecorridor.com/ru/press-tsentr/novosti")

    assert len(entries) == 2  # дубликат и пагинация отброшены
    first = entries[0]
    assert first.source == "middlecorridor.com"
    assert first.url == "https://middlecorridor.com/ru/press-tsentr/novosti/26-06-2026"
    assert first.title == "TITR на Transport Logistic Shanghai 2026"
    assert first.published_at == datetime(2026, 6, 26, tzinfo=UTC)
    assert entries[1].title == "Новое партнёрство ассоциации"
    await client.aclose()


async def test_middlecorridor_scraper_clips_long_slug_and_url() -> None:
    listing = "https://middlecorridor.com/ru/press-tsentr/novosti"
    html = (
        f'<a href="/ru/press-tsentr/novosti/{"s" * 300}"><h3>Длинный слаг</h3></a>'
        f'<a href="/ru/press-tsentr/novosti/{"x" * 1100}"><h3>Слишком длинная ссылка</h3></a>'
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    entries = await MiddleCorridorScraper(client=client).fetch(listing)
    await client.aclose()

    assert [e.title for e in entries] == ["Длинный слаг"]
    assert len(entries[0].external_id or "") == 256


def test_scraper_matches_only_middlecorridor() -> None:
    assert MiddleCorridorScraper.matches("https://middlecorridor.com/ru/press-tsentr/novosti")
    assert not MiddleCorridorScraper.matches("https://astanatimes.com/feed/")


# --- Перевод новостей -------------------------------------------------------------


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None

    async def translate(self, title: str, summary: str | None) -> tuple[str, str | None]:
        self.calls.append(title)
        if self.error is not None:
            raise self.error
        return f"RU: {title}", f"RU: {summary}" if summary else None


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, text: str) -> None:
        self.messages.append(text)


class FakeNewsProvider:
    def __init__(self, entries: list[NewsEntry]) -> None:
        self._entries = entries

    async def fetch(self, feed_url: str) -> list[NewsEntry]:
        return self._entries


def _entry(url: str, title: str, summary: str | None = None) -> NewsEntry:
    return NewsEntry(
        source="example.com",
        url=url,
        title=title,
        summary=summary,
        published_at=datetime.now(UTC) - timedelta(hours=1),
    )


def test_needs_translation_heuristic() -> None:
    ru = NewsItem(source="s", url="u1", title="Объёмы выросли")
    en = NewsItem(source="s", url="u2", title="TITR sets cargo record")
    translated = NewsItem(source="s", url="u3", title="Done", title_ru="Готово")
    assert needs_translation(ru) is False
    assert needs_translation(en) is True
    assert needs_translation(translated) is False


async def test_english_news_translated_before_publish(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
) -> None:
    translator = FakeTranslator()
    sink = FakeSink()
    service = NewsFeedService(
        session_factory,
        FakeNewsProvider(
            [
                _entry("https://e/en", "Cargo volumes doubled", "Details inside"),
                _entry("https://e/ru", "Объёмы удвоились"),
            ]
        ),
        sources=["https://example.com/feed"],
        sink=sink,
        translator=translator,
    )
    await service.run_once()

    assert translator.calls == ["Cargo volumes doubled"]  # русскую не трогали
    items = {i.url: i for i in (await session.execute(select(NewsItem))).scalars()}
    assert items["https://e/en"].title_ru == "RU: Cargo volumes doubled"
    assert items["https://e/ru"].title_ru is None

    en_message = next(m for m in sink.messages if "e/en" in m)
    assert "RU: Cargo volumes doubled" in en_message  # публикуется перевод


async def test_translation_failure_publishes_original(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
) -> None:
    translator = FakeTranslator()
    translator.error = RuntimeError("api down")
    sink = FakeSink()
    service = NewsFeedService(
        session_factory,
        FakeNewsProvider([_entry("https://e/en", "Cargo volumes doubled")]),
        sources=["https://example.com/feed"],
        sink=sink,
        translator=translator,
    )
    await service.run_once()

    assert len(sink.messages) == 1
    assert "Cargo volumes doubled" in sink.messages[0]  # оригинал, публикация не сорвалась


async def test_long_llm_title_clipped_to_column(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
) -> None:
    class VerboseTranslator:
        async def translate(self, title: str, summary: str | None) -> tuple[str, str | None]:
            return "Я" * 2000, None

    service = NewsFeedService(
        session_factory,
        FakeNewsProvider([_entry("https://e/long", "Cargo volumes doubled")]),
        sources=["https://example.com/feed"],
        sink=FakeSink(),
        translator=VerboseTranslator(),
    )
    await service.run_once()

    item = (await session.execute(select(NewsItem))).scalar_one()
    assert item.title_ru == "Я" * 512  # String(512): Postgres отверг бы длиннее


def test_format_news_prefers_russian() -> None:
    item = NewsItem(
        source="astanatimes.com",
        url="https://e/x",
        title="Original title",
        summary="Original summary",
        title_ru="Русский заголовок",
        summary_ru="Русское описание",
    )
    text = format_news_item(item)
    assert "Русский заголовок" in text
    assert "Original title" not in text


# --- Telegram-вебхук ---------------------------------------------------------------


async def test_telegram_webhook_secret_and_503() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings=settings, telegram_webhook_secret="hook-secret")
    transport = httpx.ASGITransport(app=app)
    update = {"update_id": 1}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        no_secret = await client.post("/telegram/webhook", json=update)
        assert no_secret.status_code == 403

        wrong = await client.post(
            "/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
        )
        assert wrong.status_code == 403

        # секрет верен, но бот не запущен (bot=None) → 503
        right = await client.post(
            "/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        )
        assert right.status_code == 503


class _SlowFailingDispatcher:
    """Хендлер долго думает и в конце падает — как /poll_news при сбое."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.updates: list[int] = []

    async def feed_update(self, bot: object, update: object) -> None:
        self.updates.append(update.update_id)  # type: ignore[attr-defined]
        await self.release.wait()
        raise RuntimeError("handler crashed")


async def test_telegram_webhook_acks_before_handler_finishes() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    dispatcher = _SlowFailingDispatcher()
    app = create_app(
        settings=settings,
        bot=object(),  # type: ignore[arg-type]
        dispatcher=dispatcher,  # type: ignore[arg-type]
        telegram_webhook_secret="hook-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 7},
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        )
    # 200 сразу, хендлер ещё работает: Telegram не повторит апдейт
    assert response.status_code == 200 and response.json() == {"ok": True}
    pending = list(telegram_routes._background)  # noqa: SLF001
    assert len(pending) == 1 and not pending[0].done()
    await asyncio.sleep(0)
    assert dispatcher.updates == [7]

    # падение хендлера не всплывает наружу и не оставляет висящих задач
    dispatcher.release.set()
    await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.sleep(0)
    assert not telegram_routes._background  # noqa: SLF001


async def test_telegram_webhook_disabled_when_no_secret() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings=settings, telegram_webhook_secret="")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": ""},
        )
        assert response.status_code in (403, 503)  # пустой секрет никогда не пропускает
