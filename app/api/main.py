"""FastAPI-приложение: health, вебхуки, JSON-API карты и раздача фронта."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import AccountsServices
from app.api.limits import BodyLimitMiddleware
from app.api.routes.accounts import router as accounts_router
from app.api.routes.health import router as health_router
from app.api.routes.telegram import router as telegram_router
from app.api.routes.v1 import router as v1_router
from app.api.routes.webhooks import router as webhooks_router
from app.config import Settings, get_settings
from app.services.ais_tracker import AISStreamWorker, AISTrackerService
from app.services.map_snapshot import MapSnapshotService
from app.services.predictor_accuracy import PredictorAccuracyService


def create_app(
    engine: AsyncEngine | None = None,
    settings: Settings | None = None,
    ais_tracker: AISTrackerService | None = None,
    ais_worker: AISStreamWorker | None = None,
    bot: Bot | None = None,
    dispatcher: Dispatcher | None = None,
    telegram_webhook_secret: str = "",
    map_service: MapSnapshotService | None = None,
    accuracy_service: PredictorAccuracyService | None = None,
    accounts: AccountsServices | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if accounts is not None:
            await accounts.aclose()  # дослать уведомления, закрыть клиентов APNs/почты

    app = FastAPI(title="mc-status", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = settings or get_settings()
    app.state.ais_tracker = ais_tracker
    app.state.ais_worker = ais_worker
    app.state.bot = bot
    app.state.dispatcher = dispatcher
    app.state.telegram_webhook_secret = telegram_webhook_secret
    app.state.map_service = map_service
    app.state.accuracy_service = accuracy_service  # None — нет БД (MOCK_DATA)
    app.state.accounts = accounts  # None — аккаунты выключены, их роуты отвечают 404
    app.add_middleware(BodyLimitMiddleware)  # 64 КБ на auth/me/my/orgs/admin
    if app.state.settings.cors_origins:
        # фронт на другом домене (Vercel) ходит в /api/v1 напрямую; аккаунтам нужны
        # методы записи и заголовок Authorization
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app.state.settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(telegram_router)
    app.include_router(v1_router)
    app.include_router(accounts_router)

    # Собранный фронт (web/dist) — последним, чтобы явные роуты имели приоритет
    dist = Path(app.state.settings.web_dist_dir) if app.state.settings.web_dist_dir else None
    if dist is not None and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
