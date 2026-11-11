"""Грузы аккаунта из базы как ShipmentSource — для той же проекции, что у мока.

Только видимые принципалу грузы; без принципала — пусто (никогда «все»).
Публичный снимок этот источник не использует.
"""

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CheckpointEventKind, ShipmentEventRow, ShipmentRow
from app.db.repositories.accounts import AccountsRepository, aware
from app.services.accounts.access import Principal, visible_shipment_ids
from app.services.cargo import CargoManifest, DangerousGoods
from app.services.schedule import plan_legs
from app.services.tracking import EventKind, ShipmentPlan, TrackingEvent

log = structlog.get_logger()

HOLD_OTHER = "other"


def _manifest(row: ShipmentRow) -> CargoManifest | None:
    data = row.cargo_manifest
    if not data:
        return None
    try:
        fields = dict(data)
        fields["dangerous"] = tuple(DangerousGoods(**d) for d in fields.get("dangerous") or ())
        return CargoManifest(**fields)
    except (TypeError, ValueError):
        log.warning("shipment_manifest_invalid", shipment_id=row.id)
        return None


_KIND_ORDER = {
    CheckpointEventKind.arrived: 0,
    CheckpointEventKind.held: 1,
    CheckpointEventKind.released: 2,
    CheckpointEventKind.departed: 3,
}


def _ordered(events: list[ShipmentEventRow], route: list[str]) -> list[ShipmentEventRow]:
    """События маршрута по времени; при равном — по узлу маршрута, затем прибыл < стоит <
    снят < убыл, затем id (иначе исправленное «прибыл» после «убыл» в ту же минуту
    откатывает груз назад)."""
    index = {code: i for i, code in enumerate(route)}
    return sorted(
        (e for e in events if e.node_code in index),
        key=lambda e: (aware(e.occurred_at), index[e.node_code], _KIND_ORDER[e.kind], e.id),
    )


def _departed_event(e: ShipmentEventRow, ts: datetime) -> TrackingEvent:
    note, code = e.note, None
    if e.vessel:
        note = note or f"погружен на судно «{e.vessel}»"
        code = "loaded_on_vessel"
    return TrackingEvent(
        EventKind.departed, e.node_code, ts, note, note_code=code, note_vessel=e.vessel
    )


def _scan(
    events: list[ShipmentEventRow], route: list[str]
) -> tuple[list[TrackingEvent], ShipmentEventRow | None, int, bool]:
    """События проекции, открытая стоянка и дальний достигнутый узел (индекс, -1 — нет).

    held — груз в узле: если последнее событие не «прибыл туда», добавляется прибытие.
    Стоянка, которая не может относиться к текущему положению (узел раньше дальнего
    достигнутого или оттуда уже убыл), игнорируется. Стоянку закрывает released на её
    узле, отправление из её узла или дальше, прибытие в узел дальше по маршруту.
    """
    index = {code: i for i, code in enumerate(route)}
    result: list[TrackingEvent] = []
    holds: dict[str, ShipmentEventRow] = {}
    reached, departed = -1, False  # дальний достигнутый узел и убыли ли из него

    def close(upto: int) -> None:
        for code in [c for c in holds if index[c] <= upto]:
            del holds[code]

    for e in events:
        i = index[e.node_code]
        ts = aware(e.occurred_at)
        if e.kind == CheckpointEventKind.arrived:
            result.append(TrackingEvent(EventKind.arrived, e.node_code, ts, e.note))
            close(i - 1)
            if i > reached:
                reached, departed = i, False
        elif e.kind == CheckpointEventKind.departed:
            if e.node_code != route[-1]:
                result.append(_departed_event(e, ts))
            close(i)
            if i >= reached:
                reached, departed = i, True
        elif e.kind == CheckpointEventKind.released:
            holds.pop(e.node_code, None)
        elif e.kind == CheckpointEventKind.held:
            if i < reached or (i == reached and departed):
                continue
            last = result[-1] if result else None
            if last is None or last.kind != EventKind.arrived or last.node_code != e.node_code:
                result.append(TrackingEvent(EventKind.arrived, e.node_code, ts))
            close(i - 1)
            holds[e.node_code] = e
            reached, departed = i, False
    hold = max(holds.values(), key=lambda e: (aware(e.occurred_at), e.id), default=None)
    return result, hold, reached, departed


def _replay(
    events: list[ShipmentEventRow], route: list[str]
) -> tuple[list[TrackingEvent], ShipmentEventRow | None]:
    result, hold, _, _ = _scan(events, route)
    return result, hold


def open_hold(events: list[ShipmentEventRow], route: list[str]) -> ShipmentEventRow | None:
    """Открытая стоянка по живым событиям груза (любой порядок на входе)."""
    return _scan(_ordered(events, route), route)[1]


def furthest_reached(events: list[ShipmentEventRow], route: list[str]) -> int:
    """Индекс дальнего узла маршрута, достигнутого живыми событиями (-1 — ни одного)."""
    return _scan(_ordered(events, route), route)[2]


def reach_state(events: list[ShipmentEventRow], route: list[str]) -> tuple[int, bool]:
    """Дальний достигнутый узел и убыл ли груз из него (тот же `_scan`)."""
    _, _, reached, departed = _scan(_ordered(events, route), route)
    return reached, departed


def build_db_plan(row: ShipmentRow, client: str, events: list[ShipmentEventRow]) -> ShipmentPlan:
    route = list(row.route)
    events = _ordered(events, route)
    nexts = dict(zip(route, route[1:], strict=False))
    vessels = {
        (e.node_code, nexts[e.node_code]): e.vessel
        for e in events
        if e.kind == CheckpointEventKind.departed and e.vessel and e.node_code in nexts
    }
    tracking, hold = _replay(events, route)
    hold_fields: dict[str, Any] = {}
    if hold is not None:
        other = hold.hold_code == HOLD_OTHER
        hold_fields = {
            "hold_code": None if other else hold.hold_code,
            "hold_reason": hold.note if other else None,
            "hold_node": hold.node_code,
        }
    return ShipmentPlan(
        ref=row.ref,
        client=client,
        cargo=row.cargo or "",
        cargo_en=row.cargo_en,
        legs=plan_legs(route, aware(row.planned_departure_at), vessels),
        events=tuple(tracking),
        cargo_manifest=_manifest(row),
        **hold_fields,
    )


class DbShipmentSource:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        principal: Principal | None,
    ) -> None:
        self._sf = session_factory
        self._principal = principal

    async def list_plans(self, at: datetime | None = None) -> list[ShipmentPlan]:
        if self._principal is None:
            return []
        async with self._sf() as session:
            repo = AccountsRepository(session)
            ids = await visible_shipment_ids(session, self._principal)
            rows = [
                r
                for r in await repo.shipments_by_ids(ids)
                if r.planned_departure_at is not None and len(r.route or []) >= 2
            ]
            events = await repo.live_events([r.id for r in rows])
            names = await repo.org_names({r.org_id for r in rows})
        by_shipment: dict[int, list[ShipmentEventRow]] = {}
        for e in events:
            if at is None or aware(e.occurred_at) <= at:
                by_shipment.setdefault(e.shipment_id, []).append(e)
        return [build_db_plan(r, names.get(r.org_id, ""), by_shipment.get(r.id, [])) for r in rows]
