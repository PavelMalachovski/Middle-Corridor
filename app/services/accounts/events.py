"""События на чекпоинтах: прибыл, убыл, стоянка, снятие; правка — новая запись.

Порядок и открытая стоянка считаются теми же функциями, что строят проекцию
(`db_source`), — второго алгоритма нет.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CheckpointEventKind as Kind
from app.db.models import ShipmentEventRow, ShipmentRow
from app.db.repositories.accounts import AccountsRepository, audit, aware
from app.services.accounts.access import Principal, event_nodes
from app.services.accounts.db_source import _ordered, furthest_reached, open_hold
from app.services.accounts.shipments import load_shipment

log = structlog.get_logger()

HOLD_CODES = frozenset({"weather_ban", "customs_wait", "ferry_loading_wait", "other"})
FUTURE_SLACK = timedelta(minutes=5)
NOTE_MAX, VESSEL_MAX = 500, 64
_MOVING = (Kind.arrived, Kind.departed, Kind.held)

OnEvent = Callable[[ShipmentEventRow, ShipmentRow, int], Awaitable[None]]


@dataclass(frozen=True)
class EventView:
    row: ShipmentEventRow
    superseded: bool


def _check_fields(kind: Kind, hold_code: str | None, note: str | None, vessel: str | None) -> None:
    if kind == Kind.held:
        if not hold_code:
            raise ValueError("hold_code_required")
        if hold_code not in HOLD_CODES:
            raise ValueError("bad_hold_code")
    elif hold_code is not None:
        raise ValueError("bad_hold_code")
    if note is not None and len(note) > NOTE_MAX:
        raise ValueError("note_too_long")
    if vessel is not None and len(vessel) > VESSEL_MAX:
        raise ValueError("vessel_too_long")


class EventService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime],
        on_event: OnEvent | None = None,
    ) -> None:
        self._sf = session_factory
        self._clock = clock
        self._on_event = on_event

    async def add(  # noqa: PLR0913 — поля события
        self,
        actor: Principal,
        ref: str,
        *,
        kind: Kind,
        node_code: str,
        occurred_at: datetime | None = None,
        hold_code: str | None = None,
        note: str | None = None,
        vessel: str | None = None,
        supersedes_id: int | None = None,
    ) -> ShipmentEventRow:
        now = self._clock()
        async with self._sf() as session:
            shipment, access = await load_shipment(session, actor, ref, manage=False)
            if shipment.archived_at is not None:
                raise ValueError("archived")
            route = list(shipment.route or ())
            if node_code not in route or node_code not in event_nodes(actor, access):
                raise ValueError("node_not_allowed")
            kind = Kind(kind)
            _check_fields(kind, hold_code, note, vessel)
            when = aware(occurred_at) if occurred_at is not None else now
            if when > now + FUTURE_SLACK:
                raise ValueError("in_future")

            live = await AccountsRepository(session).live_events([shipment.id])
            old = None
            if supersedes_id is not None:
                old = next((e for e in live if e.id == supersedes_id), None)
                if old is None:
                    raise ValueError("bad_supersedes")
                if old.node_code not in event_nodes(actor, access):
                    raise ValueError("node_not_allowed")
            others = [e for e in live if old is None or e.id != old.id]
            self._check_order(live, others, old, route, when, kind, node_code)

            event = ShipmentEventRow(
                shipment_id=shipment.id,
                kind=kind,
                node_code=node_code,
                occurred_at=when,
                hold_code=hold_code,
                note=note,
                vessel=vessel,
                source="manual",
                created_by=actor.user_id,
                supersedes_id=supersedes_id,
                created_at=now,
            )
            session.add(event)
            await session.flush()
            await audit(
                session,
                "event.add",
                "shipment_event",
                at=now,
                entity_id=event.id,
                user_id=actor.user_id,
                details={
                    "event_id": event.id,
                    "kind": kind.value,
                    "node": node_code,
                    "supersedes_id": supersedes_id,
                },
            )
            await session.commit()
        if self._on_event is not None:
            try:
                await self._on_event(event, shipment, actor.user_id)
            except Exception:
                log.exception("event_callback_failed", shipment_id=shipment.id, event_id=event.id)
        return event

    @staticmethod
    def _check_order(  # noqa: PLR0913
        live: list[ShipmentEventRow],
        others: list[ShipmentEventRow],
        old: ShipmentEventRow | None,
        route: list[str],
        when: datetime,
        kind: Kind,
        node_code: str,
    ) -> None:
        ordered = _ordered(others, route)
        if old is None:
            previous = ordered[-1] if ordered else None
        else:  # исправление: относительно живого события перед исправляемым
            full = _ordered(live, route)
            position = next((n for n, e in enumerate(full) if e.id == old.id), None)
            previous = full[position - 1] if position else None
        if previous is not None and when < aware(previous.occurred_at):
            raise ValueError("out_of_order")
        if kind in _MOVING and route.index(node_code) < furthest_reached(others, route):
            raise ValueError("backwards")
        if kind == Kind.released:
            hold = open_hold(others, route)
            if hold is None or hold.node_code != node_code:
                raise ValueError("no_open_hold")

    async def list(self, actor: Principal, ref: str) -> list[EventView]:
        async with self._sf() as session:
            shipment, _ = await load_shipment(session, actor, ref, manage=False)
            repo = AccountsRepository(session)
            rows = await repo.all_events(shipment.id)
        superseded = {e.supersedes_id for e in rows if e.supersedes_id is not None}
        route = list(shipment.route or ())
        index = {code: i for i, code in enumerate(route)}
        known = [e for e in rows if e.node_code in index]
        views = [EventView(e, e.id in superseded) for e in _ordered(known, route)]
        return views + [EventView(e, e.id in superseded) for e in rows if e.node_code not in index]
