from datetime import UTC, datetime

import pytest

from app.integrations.mock.fleet import ROUTE_KOSTANAY, build_plan
from app.services.schedule import DWELL_H, plan_legs, validate_route
from app.services.tracking import EventKind

START = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)


def test_plan_legs_matches_mock_build_plan():
    vessels = {("KOPER", "AMBARLI"): "MSC Test"}
    mock = build_plan(
        "T-1", "c", "x", ROUTE_KOSTANAY, EventKind.departed, ROUTE_KOSTANAY[0], START,
        vessels=vessels,
    )  # fmt: skip
    legs = plan_legs(ROUTE_KOSTANAY, START, vessels)
    assert legs == mock.legs
    assert legs[0].depart_at == START
    assert legs[1].vessel == "MSC Test"
    # между плечами — стоянка по типу узла
    assert (legs[1].depart_at - legs[0].arrive_at).total_seconds() / 3600 in DWELL_H.values()


def test_validate_route_rejects_gap_and_repeat():
    validate_route(ROUTE_KOSTANAY)
    with pytest.raises(ValueError, match="KOPER"):
        validate_route(["KOPER"])
    with pytest.raises(ValueError, match="POTI.*AKTAU"):
        validate_route(["TBILISI", "POTI", "AKTAU"])  # нет плеча Поти → Актау
    with pytest.raises(ValueError, match="POTI"):
        validate_route(["POTI", "TBILISI", "POTI"])
    with pytest.raises(ValueError, match="NOWHERE"):
        validate_route(["POTI", "NOWHERE"])
