"""Вебхуки внешних провайдеров.

POST /webhooks/vesselapi — события портов (arrival/departure) от VesselAPI.
Защита: заголовок X-Webhook-Secret должен совпадать с VESSELAPI_WEBHOOK_SECRET;
если секрет в конфиге пуст, вебхук выключен (403).
"""

from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.db.models import PortEventType

logger = structlog.get_logger(__name__)

router = APIRouter()


class VesselApiEvent(BaseModel):
    mmsi: int
    event: Literal["arrival", "departure"]
    port_code: str
    timestamp: datetime | None = None


@router.post("/webhooks/vesselapi")
async def vesselapi_webhook(
    event: VesselApiEvent,
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = request.app.state.settings
    if (
        not settings.vesselapi_webhook_secret
        or x_webhook_secret != settings.vesselapi_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="invalid webhook secret")

    tracker = request.app.state.ais_tracker
    if tracker is None:
        raise HTTPException(status_code=503, detail="ais tracker is not running")

    stored = await tracker.handle_port_event(
        mmsi=event.mmsi,
        port_code=event.port_code,
        event_type=PortEventType(event.event),
        ts=event.timestamp,
    )
    return {"stored": stored}
