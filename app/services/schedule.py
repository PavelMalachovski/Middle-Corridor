"""План отправки по типичным временам плеч и стоянкам в узлах.

Одна раскладка на мок (`build_plan`) и на грузы из базы: плечо — `typical_hours`
сегмента коридора, стоянка в узле — по его типу (`DWELL_H`).
"""

from datetime import datetime, timedelta

from app.services.corridor import NODES, NodeKind, segment
from app.services.tracking import PlannedLeg

DWELL_H = {NodeKind.rail: 6.0, NodeKind.port: 12.0, NodeKind.border: 18.0}


def validate_route(route: list[str]) -> None:
    """≥2 узлов коридора, без повторов, каждая пара — плечо коридора; иначе ValueError."""
    if len(route) < 2:
        raise ValueError(f"маршрут короче двух узлов: {route}")
    unknown = [code for code in route if code not in NODES]
    if unknown:
        raise ValueError(f"неизвестные узлы: {', '.join(unknown)}")
    repeated = sorted({code for code in route if route.count(code) > 1})
    if repeated:
        raise ValueError(f"узлы повторяются: {', '.join(repeated)}")
    for a, b in zip(route, route[1:], strict=False):
        try:
            segment(a, b)
        except KeyError:
            raise ValueError(f"нет плеча {a} → {b}") from None


def leg_offsets(route: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Часы отправления и прибытия по узлам от отправления из первого узла."""
    depart: dict[str, float] = {route[0]: 0.0}
    arrive: dict[str, float] = {}
    t = 0.0
    for a, b in zip(route, route[1:], strict=False):
        t += segment(a, b).typical_hours
        arrive[b] = t
        t += DWELL_H[NODES[b].kind]
        depart[b] = t
    return depart, arrive


def plan_legs(
    route: list[str],
    departure: datetime,
    vessels: dict[tuple[str, str], str] | None = None,
) -> tuple[PlannedLeg, ...]:
    """Плечи маршрута при отправлении из первого узла в departure."""
    vessels = vessels or {}
    depart, arrive = leg_offsets(route)
    return tuple(
        PlannedLeg(
            from_code=a,
            to_code=b,
            depart_at=departure + timedelta(hours=depart[a]),
            arrive_at=departure + timedelta(hours=arrive[b]),
            vessel=vessels.get((a, b)),
        )
        for a, b in zip(route, route[1:], strict=False)
    )
