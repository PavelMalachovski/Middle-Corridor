"""FastAPI-приложение: health, вебхуки, внутренний API."""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes.health import router as health_router


def create_app(engine: AsyncEngine | None = None) -> FastAPI:
    app = FastAPI(title="mc-status", docs_url=None, redoc_url=None)
    app.state.engine = engine
    app.include_router(health_router)
    return app
