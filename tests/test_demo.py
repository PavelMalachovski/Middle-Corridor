"""Демо-режим мока: часы со сдвигом, история MC-26-0398, /api/v1/demo/clock."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from app.integrations.mock.clock import MockClock
from app.integrations.mock.corridor import MockNodeSource
from app.integrations.mock.fleet import MockShipmentSource
from app.integrations.mock.story import DemoStory
from app.main import build_map_service
from app.services.tracking import ShipmentState, project_shipment
from app.services.weather_predictor import WindThresholds, evaluate_level

NOW = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
H = timedelta(hours=1)


def _clock(scale: float = 1.0) -> tuple[MockClock, list[datetime]]:
    wall = [NOW]
    return MockClock(scale, real=lambda: wall[0]), wall


def test_clock_advance_shifts_now() -> None:
    clock, _ = _clock()
    clock.advance(6)
    assert clock.now() == NOW + 6 * H
    assert clock.offset == 6 * H


def test_clock_scale_and_offset_add_up() -> None:
    clock, wall = _clock(scale=60)
    wall[0] = NOW + timedelta(minutes=1)
    assert clock.now() == NOW + H
    clock.advance(2)
    assert clock.now() == NOW + 3 * H


def test_clock_jump_to() -> None:
    clock, _ = _clock()
    clock.jump_to(NOW + 30 * H)
    assert clock.now() == NOW + 30 * H


def test_clock_reset_restarts_story() -> None:
    clock, wall = _clock()
    clock.advance(50)
    wall[0] = NOW + timedelta(minutes=10)
    clock.reset()
    assert clock.offset == timedelta(0)
    assert clock.story_start == clock.now() == NOW + timedelta(minutes=10)


def test_story_start_defaults_to_creation() -> None:
    clock, _ = _clock()
    assert clock.story_start == NOW


# --- история MC-26-0398 -------------------------------------------------------

T0 = NOW
THRESHOLDS = WindThresholds.from_settings(Settings(_env_file=None))


def _story() -> DemoStory:
    return DemoStory(lambda: T0)


def _at(hours: float):
    now = T0 + timedelta(hours=hours)
    return project_shipment(_story().plan(now), now)


def test_story_start_waits_for_ferry() -> None:
    s = _at(0)
    assert s.ref == "MC-26-0398"
    assert s.state == ShipmentState.waiting
    assert s.hold_code == "ferry_loading_wait"
    assert s.hold_vessel == "Azerbaijan"
    assert s.queue is not None
    # до шторма — короткая очередь: только погрузка, без погоды
    assert (s.queue.p50_hours, s.queue.p90_hours) == (12.0, 24.0)
    assert s.queue.basis_code == "ferry_wait"
    assert s.delay_hours == 18.0  # ~30 ч в Актау, по плану ушёл бы 18 ч назад


def test_story_storm() -> None:
    s = _at(6)
    assert s.hold_code == "weather_ban"
    assert s.hold_node == "AKTAU"
    assert s.queue is not None
    assert (s.queue.p50_hours, s.queue.p90_hours) == (60.0, 120.0)
    assert s.queue.basis_code == "weather_ban"
    assert s.delay_hours == 24.0  # +6 ч к старту — пуш «задержка растёт» (порог 3 ч)


def test_story_aktau_levels() -> None:
    story = _story()

    def level(hours: float) -> str | None:
        wind = story.aktau_wind(T0 + timedelta(hours=hours))
        assert wind is not None
        return evaluate_level(*wind, THRESHOLDS)

    assert level(-30) == "warning"  # с прибытия в Актау — «риск шторма», а не поле ветра
    assert level(0) == "warning"
    assert level(6) == "critical"
    assert level(65) == "critical"
    assert level(66) == "watch"
    assert story.aktau_wind(T0 + 100 * H) is None


def test_story_after_storm_waits_for_ferry_again() -> None:
    s = _at(67)  # ветер стих (watch), паром ещё грузится
    assert s.hold_code == "ferry_loading_wait"
    assert s.queue is not None and s.queue.basis_code == "ferry_wait"


def test_story_no_aktau_hold_or_queue_after_departure() -> None:
    for hours in (93, 112, 123, 144, 160):  # Алят, Гянджа, Бёюк-Кясик, Тбилиси, Поти
        s = _at(hours)
        assert s.state == ShipmentState.waiting, hours
        assert s.hold_code is None, hours
        assert s.queue is None, hours


def test_story_departs_on_ferry() -> None:
    s = _at(71)
    assert s.state == ShipmentState.in_transit
    assert s.position.on_vessel == "Azerbaijan"
    assert s.position.confirmed is False
    assert s.last_event_note_code == "loaded_on_ferry"
    assert s.queue is None


def test_story_delivered_then_cycles() -> None:
    assert _at(219).state == ShipmentState.in_transit
    assert _at(220).state == ShipmentState.delivered
    again = _at(244)
    assert again.state == ShipmentState.waiting
    assert again.hold_code == "ferry_loading_wait"


def test_story_beats_order() -> None:
    beats = _story().beats(T0)
    assert beats[0] == T0 + 6 * H
    assert all(a < b for a, b in zip(beats, beats[1:], strict=False))
    assert beats[-1] == T0 + 220 * H


def test_story_before_start_is_first_cycle() -> None:
    assert _story().cycle_start(T0 - 5 * H) == T0


def test_story_cycle_starts_on_the_hour() -> None:
    story = DemoStory(lambda: T0 + timedelta(minutes=37, seconds=12))
    assert story.cycle_start(T0 + 2 * H) == T0


async def test_mock_nodes_follow_story() -> None:
    now = T0 + 6 * H
    nodes = await MockNodeSource(lambda: now, THRESHOLDS, story=_story()).list_nodes()
    aktau = next(n for n in nodes if n.code == "AKTAU")
    assert aktau.alert_level == "critical"
    assert aktau.forecast is not None
    assert any(h.level == "critical" for h in aktau.forecast if h.ts >= now)


async def test_mock_shipments_use_story() -> None:
    now = T0
    plans = await MockShipmentSource(lambda: now, story=_story()).list_plans()
    plan = next(p for p in plans if p.ref == "MC-26-0398")
    assert project_shipment(plan, now).hold_code == "ferry_loading_wait"


async def test_no_story_keeps_0398() -> None:
    now = T0
    plans = await MockShipmentSource(lambda: now).list_plans()
    plan = next(p for p in plans if p.ref == "MC-26-0398")
    assert project_shipment(plan, now).hold_code == "weather_ban"


# --- /api/v1/demo/clock ---------------------------------------------------------


def _demo_settings(**overrides: object) -> Settings:
    base = {"mock_data": True, "demo_control": True, "web_dist_dir": ""}
    return Settings(_env_file=None, **{**base, **overrides})


@asynccontextmanager
async def _client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=settings, map_service=build_map_service(settings, None))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_demo_clock_404_without_flag() -> None:
    async with _client(_demo_settings(demo_control=False)) as client:
        assert (await client.get("/api/v1/demo/clock")).status_code == 404
        post = await client.post("/api/v1/demo/clock", json={"action": "reset"})
        assert post.status_code == 404


def test_demo_disabled_without_mock(session_factory: async_sessionmaker[AsyncSession]) -> None:
    service = build_map_service(_demo_settings(mock_data=False), session_factory)
    assert service.demo is None


async def test_demo_advance_moves_snapshot() -> None:
    async with _client(_demo_settings()) as client:
        state = await client.post("/api/v1/demo/clock", json={"action": "advance", "hours": 24})
        assert state.status_code == 200
        body = state.json()
        assert body["offset_hours"] == 24
        assert body["story_ref"] == "MC-26-0398"
        snap = (await client.get("/api/v1/snapshot")).json()
        server_time = datetime.fromisoformat(snap["server_time"])
        assert abs(server_time - (datetime.now(UTC) + 24 * H)) < timedelta(minutes=1)


async def test_demo_next_beat_storm_then_ferry() -> None:
    async with _client(_demo_settings()) as client:
        await client.post("/api/v1/demo/clock", json={"action": "reset"})
        first = (await client.get("/api/v1/shipments/MC-26-0398")).json()
        assert first["hold_code"] == "ferry_loading_wait"
        await client.post("/api/v1/demo/clock", json={"action": "next_beat"})
        storm = (await client.get("/api/v1/shipments/MC-26-0398")).json()
        assert storm["hold_code"] == "weather_ban"
        aktau = next(
            n
            for n in (await client.get("/api/v1/snapshot")).json()["nodes"]
            if n["code"] == "AKTAU"
        )
        assert aktau["alert_level"] == "critical"
        await client.post("/api/v1/demo/clock", json={"action": "next_beat"})
        sailing = (await client.get("/api/v1/shipments/MC-26-0398")).json()
        assert sailing["last_event_kind"] == "departed"
        assert sailing["last_event_note_code"] == "loaded_on_ferry"


async def test_demo_next_beat_wraps() -> None:
    async with _client(_demo_settings()) as client:
        await client.post("/api/v1/demo/clock", json={"action": "reset"})
        await client.post("/api/v1/demo/clock", json={"action": "advance", "hours": 221})
        done = (await client.get("/api/v1/shipments/MC-26-0398")).json()
        assert done["state"] == "delivered"
        await client.post("/api/v1/demo/clock", json={"action": "next_beat"})
        again = (await client.get("/api/v1/shipments/MC-26-0398")).json()
        assert again["state"] == "waiting"
        assert again["hold_code"] == "ferry_loading_wait"


async def test_demo_advance_requires_hours() -> None:
    async with _client(_demo_settings()) as client:
        missing = await client.post("/api/v1/demo/clock", json={"action": "advance"})
        assert missing.status_code == 422
        negative = await client.post("/api/v1/demo/clock", json={"action": "advance", "hours": -1})
        assert negative.status_code == 422
