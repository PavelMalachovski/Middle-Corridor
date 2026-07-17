"""WebSocket-клиент AISstream.io.

Одно подключение = один вызов stream(); реконнекты и backoff — забота
вызывающего воркера (services/ais_tracker.AISStreamWorker).

Формат сообщений: https://aisstream.io/documentation
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog
import websockets

from app.integrations.ais.base import AISPosition, AISProviderError, BoundingBox

logger = structlog.get_logger(__name__)

STREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Наиболее частые навигационные статусы AIS (ITU-R M.1371)
_NAV_STATUS = {
    0: "under_way",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuvrability",
    5: "moored",
    8: "under_way_sailing",
    15: "undefined",
}


def _parse_ts(raw: str | None) -> datetime:
    """time_utc приходит в духе "2024-01-01 10:20:30.456789 +0000 UTC"."""
    if raw:
        cleaned = raw.replace(" +0000 UTC", "+00:00").replace(" UTC", "")
        try:
            ts = datetime.fromisoformat(cleaned)
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def parse_message(data: dict) -> AISPosition | None:
    """PositionReport → AISPosition; служебные сообщения → None; ошибка → исключение."""
    if "error" in data:
        raise AISProviderError(str(data["error"]))
    if data.get("MessageType") != "PositionReport":
        return None
    meta = data.get("MetaData") or {}
    body = (data.get("Message") or {}).get("PositionReport") or {}
    try:
        nav_code = body.get("NavigationalStatus")
        return AISPosition(
            mmsi=int(meta["MMSI"]),
            lat=float(body.get("Latitude", meta.get("latitude"))),
            lon=float(body.get("Longitude", meta.get("longitude"))),
            sog=float(body["Sog"]) if body.get("Sog") is not None else None,
            cog=float(body["Cog"]) if body.get("Cog") is not None else None,
            nav_status=(_NAV_STATUS.get(nav_code, str(nav_code)) if nav_code is not None else None),
            ts=_parse_ts(meta.get("time_utc")),
            ship_name=(meta.get("ShipName") or "").strip() or None,
        )
    except (KeyError, TypeError, ValueError):
        logger.debug("ais_message_unparsed", keys=list(meta.keys()))
        return None


class AISStreamClient:
    """Реализация AISStreamProvider на AISstream.io."""

    def __init__(self, api_key: str, url: str = STREAM_URL) -> None:
        self._api_key = api_key
        self._url = url

    async def stream(
        self, boxes: list[BoundingBox], mmsi_filter: list[int] | None = None
    ) -> AsyncIterator[AISPosition]:
        subscription: dict = {
            "APIKey": self._api_key,
            "BoundingBoxes": [box.to_aisstream() for box in boxes],
            "FilterMessageTypes": ["PositionReport"],
        }
        if mmsi_filter:
            # AISstream принимает не больше 50 MMSI в фильтре
            subscription["FiltersShipMMSI"] = [str(mmsi) for mmsi in mmsi_filter[:50]]

        async with websockets.connect(self._url, ping_interval=30, ping_timeout=30) as ws:
            await ws.send(json.dumps(subscription))
            logger.info("ais_stream_connected", boxes=len(boxes), mmsi=len(mmsi_filter or []))
            async for raw in ws:
                position = parse_message(json.loads(raw))
                if position is not None:
                    yield position
