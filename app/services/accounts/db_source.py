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


def _hold(events: list[ShipmentEventRow]) -> ShipmentEventRow | None:
    """Последняя открытая стоянка: held без released на том же узле и без отправления оттуда."""
    open_holds: dict[str, ShipmentEventRow] = {}
    for e in events:
        if e.kind == CheckpointEventKind.held:
            open_holds[e.node_code] = e
        elif e.kind in {CheckpointEventKind.released, CheckpointEventKind.departed}:
            open_holds.pop(e.node_code, None)
    return max(open_holds.values(), key=lambda e: aware(e.occurred_at), default=None)


def _tracking_events(events: list[ShipmentEventRow], route: list[str]) -> list[TrackingEvent]:
    """arrived/departed → события проекции; held — значит груз в узле (прибытие, если не было)."""
    result: list[TrackingEvent] = []
    for e in events:
        if e.node_code not in route:
            continue
        ts = aware(e.occurred_at)
        if e.kind == CheckpointEventKind.arrived:
            result.append(TrackingEvent(EventKind.arrived, e.node_code, ts, e.note))
        elif e.kind == CheckpointEventKind.departed and e.node_code != route[-1]:
            note, code = e.note, None
            if e.vessel:
                note = note or f"погружен на судно «{e.vessel}»"
                code = "loaded_on_vessel"
            result.append(
                TrackingEvent(
                    EventKind.departed, e.node_code, ts, note, note_code=code, note_vessel=e.vessel
                )
            )
        elif e.kind == CheckpointEventKind.held:
            last = result[-1] if result else None
            if last is None or last.kind != EventKind.arrived or last.node_code != e.node_code:
                result.append(TrackingEvent(EventKind.arrived, e.node_code, ts))
    return result


def build_db_plan(row: ShipmentRow, client: str, events: list[ShipmentEventRow]) -> ShipmentPlan:
    route = list(row.route)
    events = sorted(events, key=lambda e: (aware(e.occurred_at), e.id))
    nexts = dict(zip(route, route[1:], strict=False))
    vessels = {
        (e.node_code, nexts[e.node_code]): e.vessel
        for e in events
        if e.kind == CheckpointEventKind.departed and e.vessel and e.node_code in nexts
    }
    hold = _hold(events)
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
        events=tuple(_tracking_events(events, route)),
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
