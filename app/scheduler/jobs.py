"""Фоновые джобы.

Подключение к APScheduler — на шаге 9. Каждую джобу можно запустить
вручную один раз:

    python -m app.scheduler.jobs weather|news|wind
"""

import asyncio
import sys

import structlog

from app.bot.main import create_bot
from app.bot.publisher import ChannelPublisher
from app.config import get_settings
from app.db.base import create_engine, create_session_factory
from app.integrations.llm.claude import ClaudeNewsTranslator
from app.integrations.news.composite import CompositeNewsProvider
from app.integrations.news.middlecorridor import MiddleCorridorScraper
from app.integrations.news.rss import RssNewsProvider
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.logging import configure_logging
from app.services.news_feed import NewsFeedService
from app.services.weather_predictor import WeatherPredictor, WindThresholds
from app.services.wind_grid import WindGridService

logger = structlog.get_logger(__name__)


async def poll_weather() -> None:
    """Один прогон погодного предиктора по всем портам."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = create_bot(settings.bot_token) if settings.bot_token else None
    sink = ChannelPublisher(bot, settings.channel_id) if bot is not None else None
    provider = OpenMeteoProvider()
    predictor = WeatherPredictor(
        session_factory, provider, WindThresholds.from_settings(settings), sink
    )
    try:
        await predictor.poll_once()
    finally:
        await provider.aclose()
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


async def poll_news() -> None:
    """Один прогон новостной ленты: сбор источников + перевод + публикация."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = create_bot(settings.bot_token) if settings.bot_token else None
    sink = ChannelPublisher(bot, settings.channel_id) if bot is not None else None
    provider = CompositeNewsProvider(RssNewsProvider(), MiddleCorridorScraper())
    translator = (
        ClaudeNewsTranslator(settings.anthropic_api_key, settings.llm_model)
        if settings.anthropic_api_key
        else None
    )
    service = NewsFeedService(
        session_factory,
        provider,
        sources=settings.news_sources,
        sink=sink,
        max_per_run=settings.news_max_per_run,
        max_age_days=settings.news_max_age_days,
        translator=translator,
    )
    try:
        await service.run_once()
    finally:
        await provider.aclose()
        if translator is not None:
            await translator.aclose()
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


async def refresh_wind_grid() -> None:
    """Один снимок поля ветра над морями (Open-Meteo по сетке) в БД."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    provider = OpenMeteoProvider()
    service = WindGridService(
        session_factory,
        provider,
        step_deg=settings.wind_grid_step_deg,
        forecast_hours=settings.wind_grid_forecast_hours,
        refresh_minutes=settings.wind_grid_refresh_minutes,
        history_hours=settings.wind_grid_history_hours,
    )
    try:
        points = await service.refresh_once()
        logger.info("wind_grid_job_done", points=points)
    finally:
        await provider.aclose()
        await engine.dispose()


JOBS = {"weather": poll_weather, "news": poll_news, "wind": refresh_wind_grid}


if __name__ == "__main__":
    job_name = sys.argv[1] if len(sys.argv) > 1 else "weather"
    settings = get_settings()
    configure_logging(settings.log_level, settings.env)
    logger.info("manual_job_run", job=job_name)
    asyncio.run(JOBS[job_name]())
