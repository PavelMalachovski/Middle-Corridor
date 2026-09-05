"""Публичный JSON-API карты (фаза 2).

GET /api/v1/snapshot?at=      — узлы, суда, отправки, маршрут, новости, сводки;
                                at — момент replay (ISO 8601), без него — живой снимок
GET /api/v1/wind?at=&step=    — поле ветра (step — шаг сетки в градусах)
GET /api/v1/shipments/{ref}   — одна отправка по номеру
GET /api/v1/stream            — SSE: событие snapshot каждые refresh_s секунд

Ответы не кешируются: фронт опрашивает snapshot каждые несколько секунд
или держит поток.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.services.map_snapshot import MapSnapshot, MapSnapshotService
from app.services.tracking import Shipment
from app.services.wind_field import WindField

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1")

T = TypeVar("T")

AtParam = Query(default=None, description="Момент replay (ISO 8601); без него — живой снимок")

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


def _replay_at(service: MapSnapshotService, at: datetime | None) -> datetime | None:
    """Нормализует at к UTC и проверяет окно replay; вне окна — 400."""
    if at is None:
        return None
    at = at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
    try:
        service.check_replay_window(at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return at


@router.get("/snapshot", response_model=MapSnapshot)
async def snapshot(
    request: Request, response: Response, at: datetime | None = AtParam
) -> MapSnapshot:
    response.headers["Cache-Control"] = "no-store"
    service = _service(request)
    return await _from_source(service.snapshot(_replay_at(service, at)))


@router.get("/wind", response_model=WindField)
async def wind(
    request: Request,
    response: Response,
    at: datetime | None = AtParam,
    step: float | None = Query(default=None, ge=0.5, le=5, description="Шаг сетки, градусы"),
) -> WindField:
    response.headers["Cache-Control"] = "no-store"
    service = _service(request)
    field = await _from_source(service.wind(_replay_at(service, at), step))
    if field is None:
        raise HTTPException(status_code=404, detail="wind field is not available")
    return field


@router.get("/shipments/{ref}", response_model=Shipment)
async def shipment(
    ref: str, request: Request, response: Response, at: datetime | None = AtParam
) -> Shipment:
    response.headers["Cache-Control"] = "no-store"
    service = _service(request)
    found = await _from_source(service.shipment(ref, _replay_at(service, at)))
    if found is None:
        raise HTTPException(status_code=404, detail="shipment not found")
    return found


async def snapshot_events(
    service: MapSnapshotService, is_disconnected: Callable[[], Awaitable[bool]]
) -> AsyncIterator[str]:
    """SSE-кадры: снимок каждые refresh_s секунд, пока клиент на связи.

    Ошибка источника не рвёт поток — уходит событием error, следующий кадр
    снова пробует. Так фронт видит причину, а не молчание.
    """
    while not await is_disconnected():
        try:
            snap = await service.snapshot()
            yield f"event: snapshot\ndata: {snap.model_dump_json()}\n\n"
        except (SQLAlchemyError, OSError) as exc:
            logger.error("map_stream_source_unavailable", error=str(exc))
            yield f"event: error\ndata: {json.dumps({'detail': SOURCE_UNAVAILABLE})}\n\n"
        await asyncio.sleep(service.live.refresh_s)


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    service = _service(request)
    if not service.live.stream:
        raise HTTPException(
            status_code=404,
            detail="поток выключен (STREAM_ENABLED=false или Vercel) — используйте поллинг",
        )
    return StreamingResponse(
        snapshot_events(service, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
