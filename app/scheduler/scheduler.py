"""Опциональный APScheduler-планировщик.

По умолчанию выключен (SCHEDULER_ENABLED=false): погода и новости
запускаются админом из бота (/poll_weather, /poll_news). Включение
флага переводит систему в автопилот без изменений кода.
"""

from collections.abc import Awaitable, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.services.news_feed import NewsFeedService
from app.services.weather_predictor import WeatherPredictor
from app.services.wind_grid import WindGridService

logger = structlog.get_logger(__name__)


def _safe(name: str, fn: Callable[[], Awaitable[object]]) -> Callable[[], Awaitable[None]]:
    """Джоба не должна ронять планировщик: ловим и логируем всё."""

    async def wrapper() -> None:
        try:
            result = await fn()
            logger.info("scheduled_job_done", job=name, result=str(result))
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduled_job_failed", job=name, error=str(exc))

    return wrapper


def create_scheduler(
    settings: Settings,
    weather_predictor: WeatherPredictor,
    news_service: NewsFeedService,
    wind_grid: WindGridService | None = None,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    if wind_grid is not None:
        scheduler.add_job(
            _safe("refresh_wind_grid", wind_grid.refresh_once),
            "interval",
            minutes=settings.wind_grid_refresh_minutes,
            id="refresh_wind_grid",
            coalesce=True,
            max_instances=1,
        )
    scheduler.add_job(
        _safe("poll_weather", weather_predictor.poll_once),
        "interval",
        minutes=settings.weather_poll_minutes,
        id="poll_weather",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _safe("poll_news", news_service.run_once),
        "interval",
        minutes=settings.news_poll_minutes,
        id="poll_news",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
