"""Права: единственное место, где решается, кто что видит и может.

Чистые функции над Principal и ShipmentAccess — без БД; загрузка — отдельно.
Нет доступа — вызывающий отвечает 404, а не 403.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OrgKind, Role, ShipmentRow, User
from app.db.repositories.accounts import AccountsRepository

_MANAGERS = frozenset({Role.owner, Role.admin})


@dataclass(frozen=True)
class MembershipView:
    org_id: int
    org_kind: OrgKind
    role: Role
    node_codes: frozenset[str]


@dataclass(frozen=True)
class Principal:
    user_id: int
    is_platform_admin: bool
    memberships: tuple[MembershipView, ...]


@dataclass(frozen=True)
class ShipmentAccess:
    org_id: int
    route: tuple[str, ...]
    shared_org_ids: frozenset[int]


async def load_principal(session: AsyncSession, user: User) -> Principal:
    rows = await AccountsRepository(session).memberships_with_kind(user.id)
    return Principal(
        user_id=user.id,
        is_platform_admin=user.is_platform_admin,
        memberships=tuple(
            MembershipView(m.org_id, o.kind, m.role, frozenset(m.node_codes or [])) for m, o in rows
        ),
    )


async def shipment_access(session: AsyncSession, row: ShipmentRow) -> ShipmentAccess:
    shared = await AccountsRepository(session).shared_org_ids(row.id)
    return ShipmentAccess(row.org_id, tuple(row.route or ()), shared)


def _owner_memberships(p: Principal, s: ShipmentAccess) -> list[MembershipView]:
    return [m for m in p.memberships if m.org_id == s.org_id]


def can_view(p: Principal, s: ShipmentAccess) -> bool:
    if p.is_platform_admin:
        return True
    for m in p.memberships:
        if m.org_id == s.org_id:
            if m.role is Role.agent and m.node_codes and not (m.node_codes & set(s.route)):
                continue
            return True
        if m.org_id in s.shared_org_ids:
            return True
    return False


def can_manage(p: Principal, s: ShipmentAccess) -> bool:
    return p.is_platform_admin or any(m.role in _MANAGERS for m in _owner_memberships(p, s))


def event_nodes(p: Principal, s: ShipmentAccess) -> frozenset[str]:
    route = frozenset(s.route)
    if can_manage(p, s):
        return route
    nodes: frozenset[str] = frozenset()
    for m in _owner_memberships(p, s):
        if m.role is Role.agent:
            nodes |= (m.node_codes & route) if m.node_codes else route
    return nodes


def can_invite(p: Principal, org_id: int) -> bool:
    return p.is_platform_admin or any(
        m.org_id == org_id and m.role in _MANAGERS for m in p.memberships
    )


def can_share_with(p: Principal, s: ShipmentAccess, client_org_id: int, linked: set[int]) -> bool:
    return can_manage(p, s) and client_org_id in linked


def creatable_orgs(p: Principal) -> list[int]:
    return [
        m.org_id for m in p.memberships if m.org_kind is OrgKind.forwarder and m.role in _MANAGERS
    ]


async def visible_shipment_ids(session: AsyncSession, p: Principal) -> list[int]:
    own = {m.org_id for m in p.memberships}
    repo = AccountsRepository(session)
    rows = await repo.candidate_shipments(None if p.is_platform_admin else own)
    mine = frozenset(own)
    return [
        shipment_id
        for shipment_id, org_id, route, shared in rows
        if can_view(p, ShipmentAccess(org_id, tuple(route), mine if shared else frozenset()))
    ]
