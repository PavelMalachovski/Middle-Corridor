"""FastAPI-приложение: health, вебхуки, внутренний API."""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes.health import router as health_router
from app.api.routes.webhooks import router as webhooks_router
from app.config import Settings, get_settings
from app.services.ais_tracker import AISStreamWorker, AISTrackerService


def create_app(
    engine: AsyncEngine | None = None,
    settings: Settings | None = None,
    ais_tracker: AISTrackerService | None = None,
    ais_worker: AISStreamWorker | None = None,
) -> FastAPI:
    app = FastAPI(title="mc-status", docs_url=None, redoc_url=None)
    app.state.engine = engine
    app.state.settings = settings or get_settings()
    app.state.ais_tracker = ais_tracker
    app.state.ais_worker = ais_worker
    app.include_router(health_router)
    app.include_router(webhooks_router)
    return app
