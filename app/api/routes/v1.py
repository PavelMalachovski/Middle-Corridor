"""Публичный JSON-API карты (фаза 2).

GET /api/v1/snapshot          — узлы, суда, отправки, маршрут, новости, сводки
GET /api/v1/wind              — поле ветра для слоя стрелок
GET /api/v1/shipments/{ref}   — одна отправка по номеру

Ответы не кешируются: фронт опрашивает snapshot каждые несколько секунд.
"""

from fastapi import APIRouter, HTTPException, Request, Response

from app.services.map_snapshot import MapSnapshot, MapSnapshotService
from app.services.tracking import Shipment
from app.services.wind_field import WindField

router = APIRouter(prefix="/api/v1")


def _service(request: Request) -> MapSnapshotService:
    service = getattr(request.app.state, "map_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="map service is not configured")
    return service


@router.get("/snapshot", response_model=MapSnapshot)
async def snapshot(request: Request, response: Response) -> MapSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return await _service(request).snapshot()


@router.get("/wind", response_model=WindField)
async def wind(request: Request, response: Response) -> WindField:
    response.headers["Cache-Control"] = "no-store"
    field = await _service(request).wind()
    if field is None:
        raise HTTPException(status_code=404, detail="wind field is not available")
    return field


@router.get("/shipments/{ref}", response_model=Shipment)
async def shipment(ref: str, request: Request, response: Response) -> Shipment:
    response.headers["Cache-Control"] = "no-store"
    found = await _service(request).shipment(ref)
    if found is None:
        raise HTTPException(status_code=404, detail="shipment not found")
    return found
