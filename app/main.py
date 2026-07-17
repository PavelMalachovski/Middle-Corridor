"""Общая точка входа: FastAPI + Telegram-бот + AIS-воркер в одном процессе.

Планировщик фоновых задач подключается на шаге 9. Компоненты включаются по
наличию конфигурации: без BOT_TOKEN — только HTTP, без AISSTREAM_API_KEY —
без AIS-стрима.
"""

import asyncio
from datetime import timedelta

import structlog
import uvicorn

from app.api.main import create_app
from app.bot.main import create_bot, create_dispatcher
from app.bot.publisher import ChannelPublisher
from app.config import get_settings
from app.db.base import create_engine, create_session_factory
from app.integrations.ais.aisstream import AISStreamClient
from app.integrations.ais.base import BoundingBox
from app.logging import configure_logging
from app.services.ais_tracker import AISStreamWorker, AISTrackerService
from app.services.manual_reports import ManualReportsService

logger = structlog.get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.env)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

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

    api_app = create_app(
        engine=engine, settings=settings, ais_tracker=ais_tracker, ais_worker=ais_worker
    )
    server = uvicorn.Server(
        uvicorn.Config(api_app, host="0.0.0.0", port=settings.port, log_config=None)
    )

    tasks: list[asyncio.Task[None]] = [asyncio.create_task(server.serve(), name="api")]
    if ais_worker is not None:
        tasks.append(asyncio.create_task(ais_worker.run(), name="ais"))
    else:
        logger.warning("aisstream_key_missing", detail="AISSTREAM_API_KEY не задан — AIS выключен")

    bot = None
    if settings.bot_token:
        bot = create_bot(settings.bot_token)
        sink = ChannelPublisher(bot, settings.channel_id)
        reports_service = ManualReportsService(session_factory, sink, settings.auto_publish_reports)
        dp = create_dispatcher(settings, reports_service)
        tasks.append(asyncio.create_task(dp.start_polling(bot, handle_signals=False), name="bot"))
        logger.info("starting", components=["api", "bot"])
    else:
        logger.warning("bot_token_missing", detail="BOT_TOKEN не задан — запускаю только API")

    try:
        # Если одна из компонент упала — гасим остальные и выходим,
        # оркестратор (Railway/Docker) перезапустит процесс целиком.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception() is not None:
                logger.error("component_failed", component=task.get_name())
                raise task.exception()  # type: ignore[misc]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
