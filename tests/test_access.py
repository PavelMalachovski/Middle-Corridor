from datetime import UTC, datetime

import pytest

from app.db.models import (
    Membership,
    Organization,
    OrgKind,
    OrgLink,
    Role,
    ShipmentRow,
    ShipmentShare,
    User,
)
from app.services.accounts.access import (
    MembershipView,
    Principal,
    ShipmentAccess,
    can_invite,
    can_manage,
    can_share_with,
    can_view,
    creatable_orgs,
    event_nodes,
    load_principal,
    shipment_access,
    visible_shipment_ids,
)

X, Y, Z = 1, 2, 3  # X — экспедитор-владелец, Y — клиент, Z — чужой экспедитор
ROUTE = ("ALMATY", "AKTAU", "POTI")
SHIP = ShipmentAccess(org_id=X, route=ROUTE, shared_org_ids=frozenset({Y}))
SHIP_NOT_SHARED = ShipmentAccess(org_id=X, route=ROUTE, shared_org_ids=frozenset())


def mv(org: int, role: Role, nodes: tuple[str, ...] = (), kind: OrgKind = OrgKind.forwarder):
    return MembershipView(org, kind, role, frozenset(nodes))


def pr(*ms: MembershipView, admin: bool = False) -> Principal:
    return Principal(user_id=1, is_platform_admin=admin, memberships=tuple(ms))


ACTIONS = ("view", "manage", "event@AKTAU", "event@POTI", "invite", "share")

# (principal, shipment, ожидаемые действия)
CASES = {
    "platform": (pr(admin=True), SHIP, set(ACTIONS)),
    "owner_x": (pr(mv(X, Role.owner)), SHIP, set(ACTIONS)),
    "admin_x": (pr(mv(X, Role.admin)), SHIP, set(ACTIONS)),
    "agent_x_aktau": (
        pr(mv(X, Role.agent, ("AKTAU",))),
        SHIP,
        {"view", "event@AKTAU"},
    ),
    "agent_x_all": (pr(mv(X, Role.agent)), SHIP, {"view", "event@AKTAU", "event@POTI"}),
    "viewer_x": (pr(mv(X, Role.viewer)), SHIP, {"view"}),
    "viewer_y_shared": (pr(mv(Y, Role.viewer, kind=OrgKind.client)), SHIP, {"view"}),
    "viewer_y_not_shared": (
        pr(mv(Y, Role.viewer, kind=OrgKind.client)),
        SHIP_NOT_SHARED,
        set(),
    ),
    "owner_z": (pr(mv(Z, Role.owner)), SHIP, set()),
}


def allowed(p: Principal, s: ShipmentAccess, action: str) -> bool:
    match action:
        case "view":
            return can_view(p, s)
        case "manage":
            return can_manage(p, s)
        case "invite":
            return can_invite(p, s.org_id)
        case "share":
            return can_share_with(p, s, Y, {Y})
        case _:
            return action.split("@")[1] in event_nodes(p, s)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("case", CASES)
def test_rights_matrix(case: str, action: str) -> None:
    p, s, expected = CASES[case]
    assert allowed(p, s, action) == (action in expected)


def test_share_requires_link() -> None:
    p = pr(mv(X, Role.owner))
    assert not can_share_with(p, SHIP, Y, set())
    assert not can_share_with(p, SHIP, Y, {Z})
    assert can_share_with(p, SHIP, Y, {Y})


def test_agent_with_foreign_nodes_cannot_view_or_mark() -> None:
    p = pr(mv(X, Role.agent, ("BAKU",)))
    assert not can_view(p, SHIP)
    assert event_nodes(p, SHIP) == frozenset()


def test_two_memberships_rights_do_not_mix() -> None:
    # admin в Z и agent[AKTAU] в X: права Z не дают ничего на груз X
    p = pr(mv(Z, Role.admin), mv(X, Role.agent, ("AKTAU",)))
    assert not can_manage(p, SHIP)
    assert not can_invite(p, X)
    assert can_invite(p, Z)
    assert event_nodes(p, SHIP) == frozenset({"AKTAU"})
    # viewer клиента Y + agent в X: шаринг даёт только просмотр
    q = pr(mv(Y, Role.viewer, kind=OrgKind.client), mv(X, Role.agent, ("POTI",)))
    assert event_nodes(q, SHIP) == frozenset({"POTI"})
    assert not can_manage(q, SHIP)


def test_creatable_orgs_only_forwarder_managers() -> None:
    p = pr(
        mv(X, Role.admin),
        mv(Z, Role.agent),
        mv(Y, Role.owner, kind=OrgKind.client),
        mv(4, Role.owner),
    )
    assert creatable_orgs(p) == [X, 4]


async def _seed(session):
    orgs = {}
    for key, kind in [("x", OrgKind.forwarder), ("y", OrgKind.client), ("z", OrgKind.forwarder)]:
        o = Organization(name=key, kind=kind)
        session.add(o)
        orgs[key] = o
    await session.flush()
    users = {}
    for key in ("owner", "agent", "agent_all", "viewer_y", "owner_z", "root", "multi"):
        u = User(email=f"{key}@e.com", is_platform_admin=key == "root")
        session.add(u)
        users[key] = u
    await session.flush()

    def member(u, o, role, nodes=()):
        session.add(Membership(user_id=u.id, org_id=o.id, role=role, node_codes=list(nodes)))

    member(users["owner"], orgs["x"], Role.owner)
    member(users["agent"], orgs["x"], Role.agent, ["POTI"])
    member(users["agent_all"], orgs["x"], Role.agent)
    member(users["viewer_y"], orgs["y"], Role.viewer)
    member(users["owner_z"], orgs["z"], Role.owner)
    member(users["multi"], orgs["z"], Role.admin)
    member(users["multi"], orgs["y"], Role.viewer)
    ships = {}
    for ref, org, route in [
        ("A", "x", ["ALMATY", "AKTAU"]),
        ("B", "x", ["AKTAU", "POTI"]),
        ("C", "z", ["POTI"]),
    ]:
        s = ShipmentRow(ref=ref, org_id=orgs[org].id, route=route)
        session.add(s)
        ships[ref] = s
    await session.flush()
    session.add(ShipmentShare(shipment_id=ships["A"].id, org_id=orgs["y"].id))
    session.add(OrgLink(forwarder_id=orgs["x"].id, client_id=orgs["y"].id))
    await session.commit()
    return orgs, users, ships


async def _visible(session, users, ships, key):
    p = await load_principal(session, users[key])
    ids = await visible_shipment_ids(session, p)
    by_id = {s.id: ref for ref, s in ships.items()}
    return [by_id[i] for i in ids]


async def test_visible_ids_by_role(session) -> None:
    _, users, ships = await _seed(session)
    assert await _visible(session, users, ships, "owner") == ["A", "B"]
    assert await _visible(session, users, ships, "agent_all") == ["A", "B"]
    assert await _visible(session, users, ships, "viewer_y") == ["A"]
    assert await _visible(session, users, ships, "owner_z") == ["C"]
    assert await _visible(session, users, ships, "root") == ["A", "B", "C"]
    assert await _visible(session, users, ships, "multi") == ["A", "C"]


async def test_agent_sees_only_routes_with_his_node(session) -> None:
    _, users, ships = await _seed(session)
    assert await _visible(session, users, ships, "agent") == ["B"]


async def test_agent_node_filter_applies_to_owner_org_shipments(session) -> None:
    _, users, ships = await _seed(session)
    # агент X [POTI]: A (без его узла) не видит, B видит
    p = await load_principal(session, users["agent"])
    assert not can_view(p, await shipment_access(session, ships["A"]))
    assert can_view(p, await shipment_access(session, ships["B"]))


async def test_archived_hidden(session) -> None:
    _, users, ships = await _seed(session)
    ships["A"].archived_at = datetime.now(UTC)
    await session.commit()
    for key in ("owner", "viewer_y", "root"):
        assert "A" not in await _visible(session, users, ships, key)


async def test_user_without_memberships_sees_nothing(session) -> None:
    u = User(email="nobody@e.com")
    session.add(u)
    await session.commit()
    p = await load_principal(session, u)
    assert await visible_shipment_ids(session, p) == []


async def test_agent_with_other_org_share_sees_shared_but_not_marks(session) -> None:
    orgs, users, ships = await _seed(session)
    u = User(email="dual@e.com")
    session.add(u)
    await session.flush()
    session.add(Membership(user_id=u.id, org_id=orgs["x"].id, role=Role.agent, node_codes=["BAKU"]))
    session.add(Membership(user_id=u.id, org_id=orgs["y"].id, role=Role.viewer, node_codes=[]))
    await session.commit()
    p = await load_principal(session, u)
    a = await shipment_access(session, ships["A"])
    assert can_view(p, a)
    assert event_nodes(p, a) == frozenset()
    assert not can_manage(p, a)
    ids = await visible_shipment_ids(session, p)
    assert ids == [ships["A"].id]  # B (не расшарена, без узла BAKU) скрыта


async def test_disabled_user_has_no_rights(session) -> None:
    _, users, ships = await _seed(session)
    for key in ("root", "owner"):
        users[key].disabled_at = datetime.now(UTC)
    await session.commit()
    for key in ("root", "owner"):
        p = await load_principal(session, users[key])
        assert await visible_shipment_ids(session, p) == []
        assert not can_view(p, await shipment_access(session, ships["A"]))
