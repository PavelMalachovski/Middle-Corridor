from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    AuditLog,
    CheckpointEventKind,
    Organization,
    OrgKind,
    OrgLink,
    Role,
    ShipmentEventRow,
    ShipmentRevision,
    ShipmentRow,
    ShipmentShare,
)
from app.integrations.mock.fleet import ROUTE_KOSTANAY
from app.services.accounts.access import MembershipView, Principal
from app.services.accounts.db_source import DbShipmentSource, build_db_plan
from app.services.accounts.errors import NotFound, PermissionDenied
from app.services.accounts.shipments import ShipmentService, iso6346_valid
from app.services.tracking import ShipmentState, project_shipment

NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
DEPART = datetime(2027, 3, 1, 8, 0, tzinfo=UTC)
CONTAINER = "CSQU3054383"


@pytest.fixture
def svc(session_factory) -> ShipmentService:
    return ShipmentService(session_factory, lambda: NOW)


@pytest.fixture
async def orgs(session) -> dict[str, int]:
    fwd = Organization(name="Fwd", kind=OrgKind.forwarder)
    linked = Organization(name="Linked client", kind=OrgKind.client)
    stranger = Organization(name="Other client", kind=OrgKind.client)
    session.add_all([fwd, linked, stranger])
    await session.flush()
    session.add(OrgLink(forwarder_id=fwd.id, client_id=linked.id))
    await session.commit()
    return {"fwd": fwd.id, "linked": linked.id, "stranger": stranger.id}


def member(org: int, role: Role, kind: OrgKind = OrgKind.forwarder, uid: int = 5) -> Principal:
    return Principal(uid, False, (MembershipView(org, kind, role, frozenset()),))


async def _create(svc: ShipmentService, actor: Principal, org_id: int, **kw):
    args = {
        "container_no": CONTAINER,
        "container_type": "40' HC",
        "route": list(ROUTE_KOSTANAY),
        "planned_departure_at": DEPART,
        "cargo": "автокомплекты",
    } | kw
    return await svc.create(actor, org_id=org_id, **args)


async def _event(session, shipment_id: int, kind, node: str, at: datetime, **kw):
    row = ShipmentEventRow(shipment_id=shipment_id, kind=kind, node_code=node, occurred_at=at, **kw)
    session.add(row)
    await session.commit()
    return row


def test_iso6346():
    assert iso6346_valid("CSQU3054383")
    assert not iso6346_valid("CSQU3054384")
    assert not iso6346_valid("CSQU305438")
    assert not iso6346_valid("1SQU3054383")
    assert iso6346_valid(" csqu 305438 3 ")
    assert not iso6346_valid("CSQU\u0663054383")  # арабско-индийская «3» — не ASCII-цифра


async def test_create_assigns_ref(svc, orgs, session):
    owner = member(orgs["fwd"], Role.owner)
    first = await _create(svc, owner, orgs["fwd"], container_no=" csqu 3054383 ")
    second = await _create(svc, owner, orgs["fwd"])
    assert first.ref == "MC-27-0001"
    assert second.ref == "MC-27-0002"
    assert first.container_no == "CSQU3054383"
    assert first.created_by == owner.user_id
    actions = [a for (a,) in (await session.execute(select(AuditLog.action))).all()]
    assert actions.count("shipment.created") == 2
    with pytest.raises(ValueError, match="bad_container"):
        await _create(svc, owner, orgs["fwd"], container_no="CSQU3054384")
    with pytest.raises(ValueError, match="bad_route"):
        await _create(svc, owner, orgs["fwd"], route=["POTI", "AKTAU"])
    with pytest.raises(ValueError, match="bad_departure"):
        await _create(svc, owner, orgs["fwd"], planned_departure_at=DEPART.replace(tzinfo=None))
    # платформа — для любого экспедитора, но не для клиента
    admin = Principal(1, True, ())
    assert (await _create(svc, admin, orgs["fwd"])).ref == "MC-27-0003"
    with pytest.raises(PermissionDenied):
        await _create(svc, admin, orgs["linked"])


async def test_agent_cannot_create(svc, orgs):
    with pytest.raises(PermissionDenied):
        await _create(svc, member(orgs["fwd"], Role.agent), orgs["fwd"])
    with pytest.raises(PermissionDenied):
        await _create(svc, member(orgs["fwd"] + 99, Role.owner), orgs["fwd"])
    with pytest.raises(PermissionDenied):
        await _create(svc, member(orgs["linked"], Role.owner, OrgKind.client), orgs["linked"])


async def test_update_writes_revision_only_changed(svc, orgs, session):
    owner = member(orgs["fwd"], Role.admin)
    row = await _create(svc, owner, orgs["fwd"])
    updated, route_changed = await svc.update(
        owner, row.ref, cargo="автокомплекты", cargo_en="car kits", container_type="20'"
    )
    assert not route_changed
    assert updated.cargo_en == "car kits"
    rev = (await session.execute(select(ShipmentRevision))).scalars().one()
    assert rev.before == {"cargo_en": None, "container_type": "40' HC"}
    assert rev.after == {"cargo_en": "car kits", "container_type": "20'"}
    assert rev.changed_by == owner.user_id
    audit = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "shipment.updated")))
        .scalars()
        .one()
    )
    assert audit.details == {"fields": ["cargo_en", "container_type"]}
    # без изменений — новой ревизии нет
    await svc.update(owner, row.ref, cargo="автокомплекты")
    assert len((await session.execute(select(ShipmentRevision))).scalars().all()) == 1
    with pytest.raises(ValueError, match="unknown_field"):
        await svc.update(owner, row.ref, org_id=orgs["linked"])
    with pytest.raises(PermissionDenied):
        await svc.update(member(orgs["fwd"], Role.agent), row.ref, cargo="x")
    with pytest.raises(NotFound):
        await svc.update(member(orgs["linked"], Role.viewer, OrgKind.client), row.ref, cargo="x")


async def test_route_edit_keeps_passed_part(svc, orgs, session):
    owner = member(orgs["fwd"], Role.owner)
    route = ["POTI", "TBILISI", "BOYUK_KASIK", "GANJA", "BAKU_ALAT", "AKTAU", "BEINEU"]
    row = await _create(svc, owner, orgs["fwd"], route=route)
    await _event(session, row.id, CheckpointEventKind.departed, "POTI", DEPART)
    wrong = await _event(
        session, row.id, CheckpointEventKind.arrived, "GANJA", DEPART + timedelta(hours=20)
    )
    await _event(
        session,
        row.id,
        CheckpointEventKind.arrived,
        "TBILISI",
        DEPART + timedelta(hours=8),
        supersedes_id=wrong.id,
    )
    # живое событие — Тбилиси (Гянджа исправлена): хвост после Тбилиси менять можно
    new_route = ["POTI", "TBILISI", "BOYUK_KASIK", "GANJA", "BAKU_ALAT", "KURYK", "BEINEU"]
    updated, route_changed = await svc.update(owner, row.ref, route=new_route)
    assert route_changed and updated.route == new_route
    with pytest.raises(ValueError, match="route_passed_part"):
        await svc.update(owner, row.ref, route=["TBILISI", "BOYUK_KASIK", "GANJA", "BAKU_ALAT"])
    with pytest.raises(ValueError, match="bad_route"):
        await svc.update(owner, row.ref, route=["POTI", "TBILISI", "AKTAU"])


async def test_share_only_linked_client(svc, orgs, session):
    owner = member(orgs["fwd"], Role.owner)
    row = await _create(svc, owner, orgs["fwd"])
    linked_viewer = member(orgs["linked"], Role.viewer, OrgKind.client, uid=7)
    with pytest.raises(NotFound):
        await svc.get(linked_viewer, row.ref)
    with pytest.raises(PermissionDenied):
        await svc.share(owner, row.ref, orgs["stranger"])
    with pytest.raises(PermissionDenied):
        await svc.share(member(orgs["fwd"], Role.agent), row.ref, orgs["linked"])
    await svc.share(owner, row.ref, orgs["linked"])
    await svc.share(owner, row.ref, orgs["linked"])  # повтор — без ошибки и дублей
    shares = (await session.execute(select(ShipmentShare))).scalars().all()
    assert [(s.shipment_id, s.org_id) for s in shares] == [(row.id, orgs["linked"])]
    assert (await svc.get(linked_viewer, row.ref)).id == row.id
    assert [r.ref for r in await svc.list_for(linked_viewer)] == [row.ref]
    actions = [a for (a,) in (await session.execute(select(AuditLog.action))).all()]
    assert actions.count("shipment.shared") == 1
    # архив: клиент больше не видит, владелец — видит
    await svc.archive(owner, row.ref)
    with pytest.raises(NotFound):
        await svc.get(linked_viewer, row.ref)
    assert (await svc.get(owner, row.ref)).archived_at is not None
    assert await svc.list_for(linked_viewer) == []
    assert "shipment.archived" in [
        a for (a,) in (await session.execute(select(AuditLog.action))).all()
    ]


async def test_projection_from_db_events_and_hold(svc, orgs, session, session_factory):
    owner = member(orgs["fwd"], Role.owner)
    row = await _create(svc, owner, orgs["fwd"])
    await _event(
        session, row.id, CheckpointEventKind.departed, "POTI", NOW - timedelta(hours=40),
        vessel=None,
    )  # fmt: skip
    await _event(
        session, row.id, CheckpointEventKind.held, "BAKU_ALAT", NOW - timedelta(hours=5),
        hold_code="weather_ban", note="шторм",
    )  # fmt: skip
    plans = await DbShipmentSource(session_factory, owner).list_plans(NOW)
    assert [p.ref for p in plans] == [row.ref]
    plan = plans[0]
    assert plan.client == "Fwd"
    assert plan.route == ROUTE_KOSTANAY
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.waiting
    assert shipment.hold_code == "weather_ban"
    assert shipment.hold_node == "BAKU_ALAT"
    assert shipment.hold_reason is None
    # снят со стоянки — открытой стоянки больше нет
    await _event(
        session, row.id, CheckpointEventKind.released, "BAKU_ALAT", NOW - timedelta(hours=1)
    )
    plan = (await DbShipmentSource(session_factory, owner).list_plans(NOW))[0]
    assert plan.hold_code is None and plan.hold_node is None
    # чужим и анониму — ничего
    stranger = member(orgs["stranger"], Role.viewer, OrgKind.client, uid=9)
    assert await DbShipmentSource(session_factory, stranger).list_plans(NOW) == []
    assert await DbShipmentSource(session_factory, None).list_plans(NOW) == []


async def test_projection_other_hold_and_vessel(svc, orgs, session, session_factory):
    owner = member(orgs["fwd"], Role.owner)
    row = await _create(svc, owner, orgs["fwd"])
    await _event(session, row.id, CheckpointEventKind.departed, "KOPER", DEPART, vessel="MSC Anna")
    await _event(
        session, row.id, CheckpointEventKind.held, "AMBARLI", NOW - timedelta(hours=2),
        hold_code="other", note="забастовка докеров",
    )  # fmt: skip
    stored = await session.get(ShipmentRow, row.id)
    stored.cargo_manifest = {
        "container_no": CONTAINER,
        "gross_kg": 18200.0,
        "dangerous": [{"un_number": "2800", "hazard_class": "8", "description": "АКБ"}],
    }
    await session.commit()
    plan = (await DbShipmentSource(session_factory, owner).list_plans(NOW))[0]
    assert plan.cargo_manifest.gross_kg == 18200.0
    assert plan.cargo_manifest.dangerous[0].un_number == "2800"
    departed = plan.events[0]
    assert departed.note_code == "loaded_on_vessel" and departed.note_vessel == "MSC Anna"
    assert plan.legs[1].vessel == "MSC Anna"
    assert plan.hold_code is None
    assert plan.hold_reason == "забастовка докеров"
    assert plan.hold_node == "AMBARLI"
    # кривой JSON манифеста — без манифеста, но груз на месте
    stored.cargo_manifest = {"weight": 1}
    await session.commit()
    plan = (await DbShipmentSource(session_factory, owner).list_plans(NOW))[0]
    assert plan.cargo_manifest is None


async def test_projection_replay_ignores_future_events(svc, orgs, session, session_factory):
    owner = member(orgs["fwd"], Role.owner)
    row = await _create(svc, owner, orgs["fwd"])
    await _event(session, row.id, CheckpointEventKind.departed, "POTI", NOW - timedelta(hours=40))
    await _event(
        session, row.id, CheckpointEventKind.held, "BAKU_ALAT", NOW - timedelta(hours=5),
        hold_code="weather_ban",
    )  # fmt: skip
    source = DbShipmentSource(session_factory, owner)
    early = NOW - timedelta(hours=10)
    plan = (await source.list_plans(early))[0]
    assert [(e.kind, e.node_code) for e in plan.events] == [("departed", "POTI")]
    assert plan.hold_code is None
    assert project_shipment(plan, early).state == ShipmentState.in_transit


async def test_create_retries_ref_race(svc, orgs, monkeypatch):
    owner = member(orgs["fwd"], Role.owner)
    await _create(svc, owner, orgs["fwd"])
    numbers = iter([1, 2])  # первый номер уже занят «соседом» — вторая попытка

    async def stale(repo, prefix):
        return next(numbers)

    monkeypatch.setattr(ShipmentService, "_next_number", staticmethod(stale))
    assert (await _create(svc, owner, orgs["fwd"])).ref == "MC-27-0002"


_K = CheckpointEventKind


def _plan(*events: tuple, route: list[str] = ROUTE_KOSTANAY):
    row = ShipmentRow(
        id=1, ref="MC-27-0001", org_id=1, route=list(route), planned_departure_at=DEPART
    )
    rows = [
        ShipmentEventRow(
            id=n, shipment_id=1, kind=kind, node_code=node, occurred_at=at, hold_code=code
        )
        for n, (kind, node, at, *rest) in enumerate(events, start=1)
        for code in [rest[0] if rest else None]
    ]
    return build_db_plan(row, "Fwd", rows)


def test_hold_closed_by_moving_on():
    plan = _plan(
        (_K.held, "GANJA", NOW - timedelta(hours=10), "customs_wait"),
        (_K.arrived, "BAKU_ALAT", NOW - timedelta(hours=2)),
    )
    assert plan.hold_code is None and plan.hold_node is None
    shipment = project_shipment(plan, NOW)
    assert shipment.state == ShipmentState.waiting
    assert shipment.position.from_code == "BAKU_ALAT"
    # отправление из узла дальше по маршруту тоже закрывает стоянку
    plan = _plan(
        (_K.held, "GANJA", NOW - timedelta(hours=10), "customs_wait"),
        (_K.departed, "BAKU_ALAT", NOW - timedelta(hours=2)),
    )
    assert plan.hold_node is None


def test_hold_that_cannot_apply_is_ignored():
    # уже убыл из узла — стоянка там задним числом не возвращает груз назад
    plan = _plan(
        (_K.departed, "POTI", NOW - timedelta(hours=10)),
        (_K.held, "POTI", NOW - timedelta(hours=5), "weather_ban"),
    )
    assert plan.hold_code is None
    assert [(e.kind, e.node_code) for e in plan.events] == [("departed", "POTI")]
    assert project_shipment(plan, NOW).state == ShipmentState.in_transit
    # стоянка в узле раньше уже достигнутого, внесённая не по порядку
    plan = _plan(
        (_K.arrived, "GANJA", NOW - timedelta(hours=10)),
        (_K.held, "TBILISI", NOW - timedelta(hours=5), "customs_wait"),
    )
    assert plan.hold_node is None
    assert [(e.kind, e.node_code) for e in plan.events] == [("arrived", "GANJA")]
    # узел вне маршрута — ни стоянки, ни прибытия
    plan = _plan((_K.held, "KURYK", NOW - timedelta(hours=5), "weather_ban"))
    assert plan.hold_node is None and plan.events == ()


def test_same_time_events_ordered_by_route_and_kind():
    at = NOW - timedelta(hours=3)
    # «убыл» внесён раньше, исправленное «прибыл» с тем же временем — позже (больший id)
    plan = _plan((_K.departed, "POTI", at), (_K.arrived, "POTI", at))
    assert [(e.kind, e.node_code) for e in plan.events] == [
        ("arrived", "POTI"),
        ("departed", "POTI"),
    ]
    assert project_shipment(plan, NOW).state == ShipmentState.in_transit
    # при равном времени узел дальше по маршруту — позже
    plan = _plan((_K.arrived, "TBILISI", at), (_K.departed, "POTI", at))
    assert [e.node_code for e in plan.events] == ["POTI", "TBILISI"]
