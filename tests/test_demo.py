"""Демо-режим мока: часы со сдвигом, история MC-26-0398, /api/v1/demo/clock."""

from datetime import UTC, datetime, timedelta

from app.integrations.mock.clock import MockClock

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
