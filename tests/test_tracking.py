"""Тесты геометрии коридора и проекции положения отправки."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.corridor import NODES, SEGMENTS, route_points, segment
from app.services.geo import haversine_km, point_along, polyline_length_km
from app.services.tracking import (
    CheckpointState,
    EventKind,
    PlannedLeg,
    PositionSource,
    ShipmentPlan,
    ShipmentState,
    TrackingEvent,
    project_shipment,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
H = timedelta(hours=1)


# --- geo / corridor ------------------------------------------------------------


def test_point_along_endpoints_and_middle() -> None:
    line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    assert point_along(line, 0.0)[0] == (0.0, 0.0)
    assert point_along(line, 1.0)[0] == (0.0, 2.0)
    (lat, lon), heading = point_along(line, 0.5)
    assert lat == pytest.approx(0.0)
    assert lon == pytest.approx(1.0)
    assert heading == pytest.approx(90.0)  # на восток


def test_segments_reference_known_nodes_and_reverse() -> None:
    for (a, b), seg in SEGMENTS.items():
        assert a in NODES and b in NODES
        assert seg.points[0] == NODES[a].latlon and seg.points[-1] == NODES[b].latlon
        assert seg.length_km > 0
    back = segment("BAKU_ALAT", "KURYK")
    assert back.points[0] == NODES["BAKU_ALAT"].latlon
    assert back.points == tuple(reversed(SEGMENTS[("KURYK", "BAKU_ALAT")].points))
    with pytest.raises(KeyError):
        segment("XIAN", "BUDAPEST")


def test_route_points_are_continuous() -> None:
    pts = route_points(["KYZYLORDA", "BEINEU", "KURYK", "BAKU_ALAT"])
    assert pts[0] == NODES["KYZYLORDA"].latlon and pts[-1] == NODES["BAKU_ALAT"].latlon
    # нет дублей на стыках сегментов
    assert all(pts[i] != pts[i + 1] for i in range(len(pts) - 1))
    assert polyline_length_km(pts) == pytest.approx(
        sum(
            segment(a, b).length_km
            for a, b in [("KYZYLORDA", "BEINEU"), ("BEINEU", "KURYK"), ("KURYK", "BAKU_ALAT")]
        )
    )


# --- projection ----------------------------------------------------------------


def _plan(
    events: list[TrackingEvent], vessel: str | None = None, hold: str | None = None
) -> ShipmentPlan:
    """Бейнеу → Курык (12 ч) → Алят (20 ч), стоянка в Курыке 12 ч."""
    t0 = NOW - 40 * H
    return ShipmentPlan(
        ref="T-1",
        client="c",
        cargo="x",
        legs=(
            PlannedLeg("BEINEU", "KURYK", t0, t0 + 12 * H),
            PlannedLeg("KURYK", "BAKU_ALAT", t0 + 24 * H, t0 + 44 * H, vessel=vessel),
        ),
        events=tuple(sorted(events, key=lambda e: e.ts)),
        hold_reason=hold,
    )


def test_not_departed_is_planned_at_origin() -> None:
    plan = _plan([TrackingEvent(EventKind.departed, "BEINEU", NOW + 5 * H)])
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.planned
    assert (shipment.position.lat, shipment.position.lon) == NODES["BEINEU"].latlon
    assert shipment.progress == 0.0
    assert shipment.checkpoints[0].state == CheckpointState.current


def test_in_transit_is_projected_between_nodes() -> None:
    plan = _plan(
        [
            TrackingEvent(EventKind.departed, "BEINEU", NOW - 30 * H),
            TrackingEvent(EventKind.arrived, "KURYK", NOW - 18 * H),
            TrackingEvent(EventKind.departed, "KURYK", NOW - 10 * H),
        ]
    )
    shipment = project_shipment(plan, NOW)
    pos = shipment.position
    assert shipment.state == ShipmentState.in_transit
    assert pos.source == PositionSource.projection and not pos.confirmed
    assert pos.leg_progress == pytest.approx(0.5)
    assert pos.mode == "sea"
    # точка лежит на ломаной сегмента: до обоих концов ближе, чем длина сегмента
    seg = segment("KURYK", "BAKU_ALAT")
    assert haversine_km((pos.lat, pos.lon), seg.points[0]) < seg.length_km
    assert haversine_km((pos.lat, pos.lon), seg.points[-1]) < seg.length_km
    assert 0.3 < shipment.progress < 0.9
    assert shipment.delay_hours == 6.0  # плановый отход из Курыка был 16 ч назад
    assert shipment.eta == plan.legs[-1].arrive_at + 6 * H
    states = [cp.state for cp in shipment.checkpoints]
    assert states == [CheckpointState.done, CheckpointState.done, CheckpointState.current]


def test_ais_position_of_vessel_wins_over_projection() -> None:
    plan = _plan(
        [
            TrackingEvent(EventKind.departed, "BEINEU", NOW - 30 * H),
            TrackingEvent(EventKind.arrived, "KURYK", NOW - 18 * H),
            TrackingEvent(EventKind.departed, "KURYK", NOW - 10 * H, "погружен на паром «Barda»"),
        ],
        vessel="Barda",
    )
    shipment = project_shipment(plan, NOW, {"Barda": (41.0, 51.0)})
    assert shipment.position.source == PositionSource.ais
    assert shipment.position.confirmed
    assert (shipment.position.lat, shipment.position.lon) == (41.0, 51.0)
    assert shipment.position.on_vessel == "Barda"
    assert "Barda" in shipment.last_event
    # без позиции парома — обычная проекция
    assert project_shipment(plan, NOW, {}).position.source == PositionSource.projection


def test_overdue_leg_stays_short_of_arrival_and_counts_delay() -> None:
    plan = _plan(
        [
            TrackingEvent(EventKind.departed, "BEINEU", NOW - 40 * H),
            TrackingEvent(EventKind.arrived, "KURYK", NOW - 28 * H),
            TrackingEvent(EventKind.departed, "KURYK", NOW - 26 * H),
        ]
    )
    shipment = project_shipment(plan, NOW)
    assert shipment.position.leg_progress == pytest.approx(0.98)
    assert shipment.delay_hours == pytest.approx(6.0)  # рейс 20 ч, идём уже 26
    assert shipment.eta == plan.legs[-1].arrive_at + 6 * H


def test_waiting_accrues_delay_and_exposes_hold() -> None:
    plan = _plan(
        [
            TrackingEvent(EventKind.departed, "BEINEU", NOW - 40 * H),
            TrackingEvent(EventKind.arrived, "KURYK", NOW - 28 * H),
        ],
        hold="Ожидание погоды",
    )
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.waiting
    assert shipment.hold_reason == "Ожидание погоды"
    assert shipment.delay_hours == pytest.approx(16.0)  # плановый отход был 16 ч назад
    assert shipment.position.source == PositionSource.event and shipment.position.confirmed
    assert shipment.position.mode is None
    assert shipment.checkpoints[1].state == CheckpointState.current
    assert shipment.checkpoints[1].actual_at == NOW - 28 * H


def test_delivered() -> None:
    plan = _plan(
        [
            TrackingEvent(EventKind.departed, "BEINEU", NOW - 60 * H),
            TrackingEvent(EventKind.arrived, "KURYK", NOW - 48 * H),
            TrackingEvent(EventKind.departed, "KURYK", NOW - 36 * H),
            TrackingEvent(EventKind.arrived, "BAKU_ALAT", NOW - 16 * H),
        ],
        hold="не должно светиться",
    )
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.delivered
    assert shipment.progress == 1.0
    assert shipment.hold_reason is None
    assert shipment.eta == NOW - 16 * H
    assert all(cp.state == CheckpointState.done for cp in shipment.checkpoints)
    assert shipment.track[0] == [NODES["BEINEU"].lon, NODES["BEINEU"].lat]
