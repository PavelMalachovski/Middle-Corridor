"""Публичный JSON-API карты (фаза 2).

GET /api/v1/snapshot          — узлы, суда, отправки, маршрут, новости, сводки
GET /api/v1/wind              — поле ветра для слоя стрелок
GET /api/v1/shipments/{ref}   — одна отправка по номеру

Ответы не кешируются: фронт опрашивает snapshot каждые несколько секунд.
"""

from collections.abc import Awaitable
from typing import TypeVar

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.services.map_snapshot import MapSnapshot, MapSnapshotService
from app.services.tracking import Shipment
from app.services.wind_field import WindField

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1")

T = TypeVar("T")

SOURCE_UNAVAILABLE = (
    "источник данных недоступен (БД не отвечает). "
    "Для демо без Postgres задайте MOCK_DATA=true и передеплойте."
)


async def _from_source(call: Awaitable[T]) -> T:
    """Ошибка БД/сети источника — это 503 с причиной, а не безликий 500."""
    try:
        return await call
    except (SQLAlchemyError, OSError) as exc:
        logger.error("map_source_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail=SOURCE_UNAVAILABLE) from exc


def _service(request: Request) -> MapSnapshotService:
    service = getattr(request.app.state, "map_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="map service is not configured")
    return service


@router.get("/snapshot", response_model=MapSnapshot)
async def snapshot(request: Request, response: Response) -> MapSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return await _from_source(_service(request).snapshot())


@router.get("/wind", response_model=WindField)
async def wind(request: Request, response: Response) -> WindField:
    response.headers["Cache-Control"] = "no-store"
    field = await _from_source(_service(request).wind())
    if field is None:
        raise HTTPException(status_code=404, detail="wind field is not available")
    return field


@router.get("/shipments/{ref}", response_model=Shipment)
async def shipment(ref: str, request: Request, response: Response) -> Shipment:
    response.headers["Cache-Control"] = "no-store"
    found = await _from_source(_service(request).shipment(ref))
    if found is None:
        raise HTTPException(status_code=404, detail="shipment not found")
    return found
