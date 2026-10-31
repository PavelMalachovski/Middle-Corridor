"""Демо-режим мока: часы со сдвигом, история MC-26-0398, /api/v1/demo/clock."""

from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.integrations.mock.clock import MockClock
from app.integrations.mock.corridor import MockNodeSource
from app.integrations.mock.fleet import MockShipmentSource
from app.integrations.mock.story import DemoStory
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
    assert (s.queue.p50_hours, s.queue.p90_hours) == (54.0, 108.0)


def test_story_storm() -> None:
    s = _at(6)
    assert s.hold_code == "weather_ban"
    assert s.hold_node == "AKTAU"
    assert s.queue is not None
    assert (s.queue.p50_hours, s.queue.p90_hours) == (60.0, 120.0)
    assert s.queue.basis_code == "weather_ban"
    assert s.delay_hours == 2.0


def test_story_aktau_levels() -> None:
    story = _story()

    def level(hours: float) -> str | None:
        wind = story.aktau_wind(T0 + timedelta(hours=hours))
        assert wind is not None
        return evaluate_level(*wind, THRESHOLDS)

    assert level(0) == "warning"
    assert level(6) == "critical"
    assert level(65) == "critical"
    assert level(66) == "watch"
    assert story.aktau_wind(T0 + 100 * H) is None


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
