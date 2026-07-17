"""Тесты AIS-модуля: парсер, фильтр по судам, троттлинг, reconnect, вебхук (§7.2)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from app.db.models import (
    CorridorLeg,
    Port,
    PortEvent,
    PortEventType,
    Vessel,
    VesselPosition,
)
from app.integrations.ais.aisstream import parse_message
from app.integrations.ais.base import AISPosition, AISProviderError, BoundingBox
from app.services.ais_tracker import AISStreamWorker, AISTrackerService

TRACKED_MMSI = 423000001
UNKNOWN_MMSI = 999999999


def _pos(mmsi: int = TRACKED_MMSI, ts: datetime | None = None) -> AISPosition:
    return AISPosition(
        mmsi=mmsi,
        lat=42.0,
        lon=50.0,
        sog=10.5,
        cog=180.0,
        nav_status="under_way",
        ts=ts or datetime.now(UTC),
    )


@pytest.fixture
async def seeded(session: AsyncSession) -> Port:
    port = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
    )
    session.add_all(
        [
            port,
            Vessel(mmsi=TRACKED_MMSI, name="Professor Gul", leg=CorridorLeg.caspian),
            Vessel(mmsi=423000002, name="Untracked", leg=CorridorLeg.caspian, is_tracked=False),
        ]
    )
    await session.commit()
    return port


@pytest.fixture
def tracker(session_factory: async_sessionmaker[AsyncSession]) -> AISTrackerService:
    return AISTrackerService(session_factory, min_save_interval=timedelta(minutes=5))


# --- Парсер AISstream ------------------------------------------------------------


def test_parse_position_report() -> None:
    message = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 423000001,
            "ShipName": "PROFESSOR GUL ",
            "latitude": 42.1,
            "longitude": 50.2,
            "time_utc": "2026-07-17 09:40:00.123456 +0000 UTC",
        },
        "Message": {
            "PositionReport": {
                "Latitude": 42.1,
                "Longitude": 50.2,
                "Sog": 11.2,
                "Cog": 95.0,
                "NavigationalStatus": 0,
            }
        },
    }
    position = parse_message(message)
    assert position is not None
    assert position.mmsi == 423000001
    assert position.ship_name == "PROFESSOR GUL"
    assert position.sog == 11.2
    assert position.nav_status == "under_way"
    assert position.ts == datetime(2026, 7, 17, 9, 40, 0, 123456, tzinfo=UTC)


def test_parse_non_position_message_is_none() -> None:
    assert parse_message({"MessageType": "ShipStaticData", "Message": {}}) is None


def test_parse_error_message_raises() -> None:
    with pytest.raises(AISProviderError, match="Api Key Is Not Valid"):
        parse_message({"error": "Api Key Is Not Valid"})


def test_bounding_box_parse() -> None:
    box = BoundingBox.parse("36.5, 47.0, 47.0, 54.5")
    assert box.to_aisstream() == [[36.5, 47.0], [47.0, 54.5]]
    with pytest.raises(ValueError):
        BoundingBox.parse("1,2,3")


# --- Трекер ---------------------------------------------------------------------


async def test_tracked_position_is_saved(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    assert await tracker.handle_position(_pos()) is True
    row = (await session.execute(select(VesselPosition))).scalar_one()
    assert row.lat == 42.0
    assert row.nav_status == "under_way"


async def test_unknown_mmsi_is_ignored(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    assert await tracker.handle_position(_pos(mmsi=UNKNOWN_MMSI)) is False
    count = (await session.execute(select(func.count(VesselPosition.id)))).scalar_one()
    assert count == 0


async def test_untracked_vessel_is_ignored(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    assert await tracker.handle_position(_pos(mmsi=423000002)) is False


async def test_positions_throttled_per_vessel(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    base = datetime.now(UTC)
    assert await tracker.handle_position(_pos(ts=base)) is True
    assert await tracker.handle_position(_pos(ts=base + timedelta(minutes=1))) is False
    assert await tracker.handle_position(_pos(ts=base + timedelta(minutes=6))) is True

    count = (await session.execute(select(func.count(VesselPosition.id)))).scalar_one()
    assert count == 2


async def test_port_event_saved_and_unknown_ignored(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    ok = await tracker.handle_port_event(
        TRACKED_MMSI, "aktau", PortEventType.arrival, datetime.now(UTC)
    )
    assert ok is True
    event = (await session.execute(select(PortEvent))).scalar_one()
    assert event.event_type is PortEventType.arrival

    assert (
        await tracker.handle_port_event(TRACKED_MMSI, "NO_SUCH_PORT", PortEventType.arrival, None)
        is False
    )
    assert (
        await tracker.handle_port_event(UNKNOWN_MMSI, "AKTAU", PortEventType.arrival, None) is False
    )


# --- Воркер: reconnect -----------------------------------------------------------


class FlakyProvider:
    """Первое подключение падает, второе отдаёт позиции, дальше — пусто."""

    def __init__(self) -> None:
        self.connects = 0

    async def stream(
        self, boxes: list[BoundingBox], mmsi_filter: list[int] | None = None
    ) -> AsyncIterator[AISPosition]:
        self.connects += 1
        if self.connects == 1:
            raise AISProviderError("connection reset")
        if self.connects == 2:
            yield _pos()
        # дальнейшие подключения сразу завершаются (сервер закрыл стрим)


async def test_worker_survives_disconnects_and_saves(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    provider = FlakyProvider()
    worker = AISStreamWorker(
        provider, tracker, [BoundingBox.parse("36.5,47.0,47.0,54.5")], initial_delay=0.01
    )
    task = asyncio.create_task(worker.run())
    try:
        for _ in range(200):  # ждём, пока воркер переживёт сбой и сохранит позицию
            await asyncio.sleep(0.01)
            if provider.connects >= 3:
                break
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert provider.connects >= 3  # упал, переподключился, продолжил
    assert worker.last_message_at is not None
    count = (await session.execute(select(func.count(VesselPosition.id)))).scalar_one()
    assert count == 1


# --- Вебхук VesselAPI -------------------------------------------------------------


async def test_vesselapi_webhook(
    tracker: AISTrackerService, session: AsyncSession, seeded: Port
) -> None:
    settings = Settings(_env_file=None, vesselapi_webhook_secret="s3cret")  # type: ignore[call-arg]
    app = create_app(engine=None, settings=settings, ais_tracker=tracker)
    transport = httpx.ASGITransport(app=app)
    payload = {"mmsi": TRACKED_MMSI, "event": "departure", "port_code": "AKTAU"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/webhooks/vesselapi", json=payload)
        assert denied.status_code == 403  # без секрета

        ok = await client.post(
            "/webhooks/vesselapi", json=payload, headers={"X-Webhook-Secret": "s3cret"}
        )
        assert ok.status_code == 200
        assert ok.json() == {"stored": True}

    event = (await session.execute(select(PortEvent))).scalar_one()
    assert event.event_type is PortEventType.departure
