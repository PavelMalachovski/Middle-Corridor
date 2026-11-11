from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    AuditLog,
    CheckpointEventKind,
    Organization,
    OrgKind,
    Role,
    ShipmentEventRow,
    ShipmentShare,
)
from app.integrations.mock.fleet import ROUTE_KOSTANAY
from app.services.accounts.access import MembershipView, Principal
from app.services.accounts.db_source import build_db_plan
from app.services.accounts.errors import NotFound
from app.services.accounts.events import EventService
from app.services.accounts.shipments import ShipmentService
from app.services.tracking import ShipmentState, project_shipment

NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
DEPART = datetime(2027, 3, 1, 8, 0, tzinfo=UTC)
K = CheckpointEventKind


def H(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def member(org: int, role: Role, nodes=(), kind=OrgKind.forwarder, uid: int = 5) -> Principal:
    return Principal(uid, False, (MembershipView(org, kind, role, frozenset(nodes)),))


@pytest.fixture
async def world(session, session_factory):
    fwd = Organization(name="Fwd", kind=OrgKind.forwarder)
    other = Organization(name="Other fwd", kind=OrgKind.forwarder)
    client = Organization(name="Client", kind=OrgKind.client)
    session.add_all([fwd, other, client])
    await session.flush()
    owner = member(fwd.id, Role.owner, uid=1)
    ship = await ShipmentService(session_factory, lambda: NOW).create(
        owner,
        org_id=fwd.id,
        container_no="CSQU3054383",
        container_type=None,
        route=list(ROUTE_KOSTANAY),
        planned_departure_at=DEPART,
        cargo="x",
    )
    session.add(ShipmentShare(shipment_id=ship.id, org_id=client.id))
    await session.commit()
    return {
        "ref": ship.ref,
        "id": ship.id,
        "owner": owner,
        "agent": member(fwd.id, Role.agent, {"POTI", "TBILISI"}, uid=2),
        "viewer": member(client.id, Role.viewer, kind=OrgKind.client, uid=3),
        "stranger": member(other.id, Role.owner, uid=4),
    }


@pytest.fixture
def calls() -> list:
    return []


@pytest.fixture
def svc(session_factory, calls) -> EventService:
    async def on_event(event, shipment, user_id):
        calls.append((event.id, shipment.ref, user_id))

    return EventService(session_factory, lambda: NOW, on_event)


async def code(coro) -> str:
    with pytest.raises(ValueError) as exc:
        await coro
    return str(exc.value)


async def test_agent_marks_own_node_only(svc, world):
    ev = await svc.add(world["agent"], world["ref"], kind=K.arrived, node_code="POTI")
    assert ev.source == "manual" and ev.created_by == 2
    assert ev.occurred_at == NOW and ev.created_at == NOW
    assert await code(svc.add(world["agent"], world["ref"], kind=K.arrived, node_code="KOPER")) == (
        "node_not_allowed"
    )
    # узла нет в маршруте — даже владельцу
    assert await code(
        svc.add(world["owner"], world["ref"], kind=K.arrived, node_code="ALMATY")
    ) == ("node_not_allowed")
    # владелец отмечает любой узел маршрута
    await svc.add(world["owner"], world["ref"], kind=K.arrived, node_code="TBILISI")
    with pytest.raises(NotFound):
        await svc.add(world["stranger"], world["ref"], kind=K.arrived, node_code="POTI")
    with pytest.raises(NotFound):
        await svc.add(world["owner"], "MC-00-9999", kind=K.arrived, node_code="POTI")


async def test_viewer_cannot_mark(svc, world, session):
    assert await code(svc.add(world["viewer"], world["ref"], kind=K.arrived, node_code="POTI")) == (
        "node_not_allowed"
    )
    assert (await session.execute(select(ShipmentEventRow))).first() is None


async def test_time_not_future_not_before_previous(svc, world):
    ref, owner = world["ref"], world["owner"]
    await svc.add(owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(5))
    future = NOW + timedelta(minutes=6)
    assert await code(
        svc.add(owner, ref, kind=K.arrived, node_code="TBILISI", occurred_at=future)
    ) == ("in_future")
    await svc.add(
        owner,
        ref,
        kind=K.arrived,
        node_code="TBILISI",
        occurred_at=NOW + timedelta(minutes=5),
    )
    assert await code(
        svc.add(owner, ref, kind=K.departed, node_code="TBILISI", occurred_at=H(6))
    ) == ("out_of_order")


async def test_held_needs_code_released_needs_hold(svc, world):
    ref, owner = world["ref"], world["owner"]
    assert await code(svc.add(owner, ref, kind=K.held, node_code="POTI")) == "hold_code_required"
    assert await code(svc.add(owner, ref, kind=K.held, node_code="POTI", hold_code="rain")) == (
        "bad_hold_code"
    )
    assert await code(svc.add(owner, ref, kind=K.arrived, node_code="POTI", hold_code="other")) == (
        "bad_hold_code"
    )
    assert await code(svc.add(owner, ref, kind=K.released, node_code="POTI")) == "no_open_hold"
    await svc.add(
        owner, ref, kind=K.held, node_code="POTI", hold_code="weather_ban", occurred_at=H(3)
    )
    assert await code(svc.add(owner, ref, kind=K.released, node_code="TBILISI")) == "no_open_hold"
    await svc.add(owner, ref, kind=K.released, node_code="POTI", occurred_at=H(1))
    assert await code(svc.add(owner, ref, kind=K.released, node_code="POTI")) == "no_open_hold"


async def test_note_vessel_limits_and_backwards(svc, world):
    ref, owner = world["ref"], world["owner"]
    assert await code(svc.add(owner, ref, kind=K.arrived, node_code="POTI", note="я" * 501)) == (
        "note_too_long"
    )
    await svc.add(owner, ref, kind=K.arrived, node_code="POTI", note="я" * 500, occurred_at=H(5))
    assert await code(
        svc.add(owner, ref, kind=K.departed, node_code="POTI", vessel="v" * 65, occurred_at=H(4))
    ) == ("vessel_too_long")
    await svc.add(owner, ref, kind=K.arrived, node_code="TBILISI", occurred_at=H(1))
    for kind in (K.arrived, K.departed):
        late = svc.add(owner, ref, kind=kind, node_code="KOPER", occurred_at=H(0.5))
        assert await code(late) == "backwards"
    assert (
        await code(
            svc.add(
                owner, ref, kind=K.held, node_code="POTI", hold_code="other", occurred_at=H(0.5)
            )
        )
        == "backwards"
    )


async def test_held_after_departed_same_node_is_backwards(svc, world, session):
    ref, owner = world["ref"], world["owner"]
    await svc.add(owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(5))
    dep = await svc.add(owner, ref, kind=K.departed, node_code="POTI", occurred_at=H(4))
    late = svc.add(
        owner, ref, kind=K.held, node_code="POTI", hold_code="weather_ban", occurred_at=H(3)
    )
    assert await code(late) == "backwards"
    # исправление «убыл» снимает событие — стоянка там снова возможна
    await svc.add(
        owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(4), supersedes_id=dep.id
    )
    await svc.add(
        owner, ref, kind=K.held, node_code="POTI", hold_code="weather_ban", occurred_at=H(3)
    )


async def _plan(session_factory, world):
    from app.db.repositories.accounts import AccountsRepository

    async with session_factory() as s:
        repo = AccountsRepository(s)
        row = await repo.shipment_by_ref(world["ref"])
        events = await repo.live_events([row.id])
        return build_db_plan(row, "Fwd", events)


async def test_correction_replaces_in_projection(svc, world, session_factory):
    ref, owner = world["ref"], world["owner"]
    wrong = await svc.add(owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(10))
    plan = await _plan(session_factory, world)
    assert [e.node_code for e in plan.events] == ["POTI"]
    fixed = await svc.add(
        owner, ref, kind=K.arrived, node_code="TBILISI", occurred_at=H(8), supersedes_id=wrong.id
    )
    plan = await _plan(session_factory, world)
    assert [e.node_code for e in plan.events] == ["TBILISI"]
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.waiting
    # агент исправляет только свои узлы
    other = await svc.add(owner, ref, kind=K.arrived, node_code="BAKU_ALAT", occurred_at=H(2))
    assert await code(
        svc.add(
            world["agent"],
            ref,
            kind=K.arrived,
            node_code="BAKU_ALAT",
            occurred_at=H(2),
            supersedes_id=other.id,
        )
    ) == ("node_not_allowed")
    # исправление проверяется относительно события перед исправляемым
    assert await code(
        svc.add(
            owner,
            ref,
            kind=K.arrived,
            node_code="BAKU_ALAT",
            occurred_at=H(9),
            supersedes_id=other.id,
        )
    ) == ("out_of_order")
    await svc.add(
        owner,
        ref,
        kind=K.arrived,
        node_code="BAKU_ALAT",
        occurred_at=H(7),
        supersedes_id=other.id,
    )
    # исправление не двигает груз назад относительно остальных живых событий
    assert await code(
        svc.add(
            owner,
            ref,
            kind=K.arrived,
            node_code="KOPER",
            occurred_at=H(7),
            supersedes_id=fixed.id,
        )
    ) == ("backwards")


async def test_superseded_chain_and_foreign_supersedes(svc, world, session):
    ref, owner = world["ref"], world["owner"]
    a = await svc.add(owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(10))
    b = await svc.add(
        owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(9), supersedes_id=a.id
    )
    # a уже исправлено — повторно исправлять нельзя
    assert await code(
        svc.add(owner, ref, kind=K.arrived, node_code="POTI", supersedes_id=a.id)
    ) == ("bad_supersedes")
    c = await svc.add(
        owner, ref, kind=K.arrived, node_code="POTI", occurred_at=H(8), supersedes_id=b.id
    )
    assert await code(
        svc.add(owner, ref, kind=K.arrived, node_code="POTI", supersedes_id=99999)
    ) == ("bad_supersedes")
    views = await svc.list(owner, ref)
    assert [(v.row.id, v.superseded) for v in views] == [(a.id, True), (b.id, True), (c.id, False)]
    # событие чужого груза
    org = world["stranger"].memberships[0].org_id
    other_ship = await ShipmentService(svc._sf, lambda: NOW).create(
        member(org, Role.owner, uid=1),
        org_id=org,
        container_no="CSQU3054383",
        container_type=None,
        route=list(ROUTE_KOSTANAY),
        planned_departure_at=DEPART,
        cargo="y",
    )
    foreign = await svc.add(
        member(org, Role.owner, uid=1),
        other_ship.ref,
        kind=K.arrived,
        node_code="POTI",
        occurred_at=H(1),
    )
    assert await code(
        svc.add(owner, ref, kind=K.arrived, node_code="POTI", supersedes_id=foreign.id)
    ) == ("bad_supersedes")
    with pytest.raises(NotFound):
        await svc.list(world["stranger"], ref)


async def test_on_event_called_after_commit_with_author(session_factory, world, calls, session):
    seen = []

    async def on_event(event, shipment, user_id):
        async with session_factory() as s:  # событие уже видно из другой сессии
            seen.append(await s.get(ShipmentEventRow, event.id) is not None)
        calls.append((event.id, shipment.ref, user_id))

    svc = EventService(session_factory, lambda: NOW, on_event)
    ev = await svc.add(world["agent"], world["ref"], kind=K.arrived, node_code="POTI")
    assert calls == [(ev.id, world["ref"], 2)] and seen == [True]
    audit = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "event.add")))
        .scalars()
        .one()
    )
    assert audit.user_id == 2 and audit.entity_id == str(ev.id)
    assert audit.details == {
        "event_id": ev.id,
        "kind": "arrived",
        "node": "POTI",
        "supersedes_id": None,
    }


async def test_on_event_failure_is_swallowed(session_factory, world, session):
    async def boom(event, shipment, user_id):
        raise RuntimeError("push down")

    svc = EventService(session_factory, lambda: NOW, boom)
    ev = await svc.add(world["owner"], world["ref"], kind=K.arrived, node_code="POTI")
    assert (await session.get(ShipmentEventRow, ev.id)) is not None


async def test_archived_shipment_rejects_events(svc, world, session_factory):
    await ShipmentService(session_factory, lambda: NOW).archive(world["owner"], world["ref"])
    assert await code(svc.add(world["owner"], world["ref"], kind=K.arrived, node_code="POTI")) == (
        "archived"
    )
    with pytest.raises(NotFound):
        await svc.add(world["agent"], world["ref"], kind=K.arrived, node_code="POTI")
