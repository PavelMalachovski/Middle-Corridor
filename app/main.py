"""Общая точка входа: FastAPI + Telegram-бот + AIS-воркер в одном процессе.

Компоненты включаются по наличию конфигурации:
- без BOT_TOKEN — только HTTP;
- без AISSTREAM_API_KEY — без AIS-стрима;
- BOT_WEBHOOK_URL задан — бот принимает апдейты вебхуком через FastAPI,
  иначе long polling (локальная разработка);
- SCHEDULER_ENABLED=true — автопилот погоды/новостей, иначе по командам админа;
- ANTHROPIC_API_KEY задан — англоязычные новости переводятся перед публикацией;
- MOCK_DATA=true — JSON-API карты (/api/v1) отдаёт синтетику без БД.
"""

import asyncio
import hashlib
from datetime import timedelta

import structlog
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.api.routes.telegram import TELEGRAM_WEBHOOK_PATH
from app.bot.main import create_bot, create_dispatcher
from app.bot.publisher import ChannelPublisher
from app.config import Settings, get_settings
from app.db.base import create_engine, create_session_factory
from app.integrations.ais.aisstream import AISStreamClient
from app.integrations.ais.base import BoundingBox
from app.integrations.llm.claude import ClaudeNewsTranslator
from app.integrations.mock.clock import MockClock
from app.integrations.mock.corridor import MockNewsSource, MockNodeSource, MockReportSource
from app.integrations.mock.fleet import MockFleetSource, MockShipmentSource
from app.integrations.mock.wind import MockWindField
from app.integrations.news.composite import CompositeNewsProvider
from app.integrations.news.middlecorridor import MiddleCorridorScraper
from app.integrations.news.rss import RssNewsProvider
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.logging import configure_logging
from app.scheduler.scheduler import create_scheduler
from app.services.ais_tracker import AISStreamWorker, AISTrackerService
from app.services.manual_reports import ManualReportsService
from app.services.map_snapshot import (
    CorridorStatusAdapter,
    DbNewsSource,
    LiveInfo,
    MapSnapshotService,
)
from app.services.news_feed import NewsFeedService
from app.services.status_aggregator import StatusAggregatorService
from app.services.weather_predictor import WeatherPredictor, WindThresholds

logger = structlog.get_logger(__name__)


def _webhook_secret(settings: Settings) -> str:
    if settings.bot_webhook_secret:
        return settings.bot_webhook_secret
    # детерминированный секрет из токена — не храним лишних значений
    return hashlib.sha256(settings.bot_token.encode()).hexdigest()[:32]


def build_map_service(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None
) -> MapSnapshotService:
    """Источники для карты: синтетика (MOCK_DATA, без БД) или агрегатор статуса + БД."""
    thresholds = WindThresholds.from_settings(settings)
    live = LiveInfo(
        stream=settings.stream_available,
        refresh_s=(
            settings.stream_interval_s if settings.stream_available else settings.poll_interval_s
        ),
        replay_past_hours=settings.replay_past_hours,
        replay_future_hours=settings.replay_future_hours,
    )
    if settings.mock_data:
        clock = MockClock(settings.mock_time_scale)
        return MapSnapshotService(
            nodes=MockNodeSource(clock.now, thresholds),
            vessels=MockFleetSource(clock.now),
            shipments=MockShipmentSource(clock.now),
            wind=MockWindField(clock.now),
            news=MockNewsSource(clock.now),
            reports=MockReportSource(clock.now),
            thresholds=thresholds,
            mock=True,
            clock=clock.now,
            live=live,
        )
    if session_factory is None:
        raise ValueError("без MOCK_DATA карте нужна БД (session_factory)")
    adapter = CorridorStatusAdapter(StatusAggregatorService(session_factory))
    # Отправки и поле ветра в проде пока без источника — фронт покажет «нет данных»
    return MapSnapshotService(
        nodes=adapter,
        vessels=adapter,
        reports=adapter,
        news=DbNewsSource(session_factory),
        thresholds=thresholds,
        live=live,
    )


async def run() -> None:  # noqa: PLR0915 — точка сборки всего приложения
    settings = get_settings()
    configure_logging(settings.log_level, settings.env)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    # --- AIS ---
    ais_tracker = AISTrackerService(
        session_factory,
        min_save_interval=timedelta(minutes=settings.ais_min_save_interval_minutes),
    )
    ais_worker = None
    if settings.aisstream_api_key:
        boxes = [
            BoundingBox.parse(settings.ais_bbox_caspian),
            BoundingBox.parse(settings.ais_bbox_black_sea),
        ]
        ais_worker = AISStreamWorker(
            AISStreamClient(settings.aisstream_api_key), ais_tracker, boxes
        )

    # --- Погода и новости (сервисы нужны и боту, и планировщику) ---
    weather_provider = OpenMeteoProvider()
    news_provider = CompositeNewsProvider(RssNewsProvider(), MiddleCorridorScraper())
    translator = (
        ClaudeNewsTranslator(settings.anthropic_api_key, settings.llm_model)
        if settings.anthropic_api_key
        else None
    )

    bot = None
    dp = None
    scheduler = None
    webhook_mode = bool(settings.bot_token and settings.bot_webhook_url)
    if settings.bot_token:
        bot = create_bot(settings.bot_token)
        sink = ChannelPublisher(bot, settings.channel_id)
        reports_service = ManualReportsService(session_factory, sink, settings.auto_publish_reports)
        status_service = StatusAggregatorService(session_factory)
        weather_predictor = WeatherPredictor(
            session_factory, weather_provider, WindThresholds.from_settings(settings), sink
        )
        news_service = NewsFeedService(
            session_factory,
            news_provider,
            sources=settings.news_sources,
            sink=sink,
            max_per_run=settings.news_max_per_run,
            max_age_days=settings.news_max_age_days,
            translator=translator,
        )
        dp = create_dispatcher(
            settings, reports_service, status_service, weather_predictor, news_service
        )
        if settings.scheduler_enabled:
            scheduler = create_scheduler(settings, weather_predictor, news_service)
        if translator is None:
            logger.info("news_translation_disabled", detail="ANTHROPIC_API_KEY не задан")
    else:
        logger.warning("bot_token_missing", detail="BOT_TOKEN не задан — запускаю только API")

    # --- HTTP ---
    map_service = build_map_service(settings, session_factory)
    if settings.mock_data:
        logger.warning("mock_data_enabled", detail="API карты отдаёт синтетику (MOCK_DATA=true)")
    api_app = create_app(
        engine=engine,
        settings=settings,
        ais_tracker=ais_tracker,
        ais_worker=ais_worker,
        bot=bot,
        dispatcher=dp,
        telegram_webhook_secret=_webhook_secret(settings) if webhook_mode else "",
        map_service=map_service,
    )
    server = uvicorn.Server(
        uvicorn.Config(api_app, host="0.0.0.0", port=settings.port, log_config=None)
    )

    tasks: list[asyncio.Task[None]] = [asyncio.create_task(server.serve(), name="api")]
    if ais_worker is not None:
        tasks.append(asyncio.create_task(ais_worker.run(), name="ais"))
    else:
        logger.warning("aisstream_key_missing", detail="AISSTREAM_API_KEY не задан — AIS выключен")

    if bot is not None and dp is not None:
        if webhook_mode:
            url = settings.bot_webhook_url.rstrip("/") + TELEGRAM_WEBHOOK_PATH
            await bot.set_webhook(
                url=url,
                secret_token=_webhook_secret(settings),
                allowed_updates=dp.resolve_used_update_types(),
            )
            logger.info("bot_webhook_set", url=url)
        else:
            # webhook мог остаться от прежнего деплоя — иначе polling конфликтует
            await bot.delete_webhook(drop_pending_updates=False)
            tasks.append(
                asyncio.create_task(dp.start_polling(bot, handle_signals=False), name="bot")
            )
        if scheduler is not None:
            scheduler.start()
            logger.info("scheduler_started", weather_min=settings.weather_poll_minutes)
        else:
            logger.info("scheduler_disabled", detail="погода/новости — по командам админа")
        logger.info("starting", mode="webhook" if webhook_mode else "polling")

    try:
        # Если одна из компонент упала — гасим остальные и выходим,
        # оркестратор (Railway/Docker) перезапустит процесс целиком.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception() is not None:
                logger.error("component_failed", component=task.get_name())
                raise task.exception()  # type: ignore[misc]
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await weather_provider.aclose()
        await news_provider.aclose()
        if translator is not None:
            await translator.aclose()
        if bot is not None:
            await bot.session.close()
        await engine.dispose()
        logger.info("shutdown_complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
