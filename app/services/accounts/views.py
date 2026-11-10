"""Представления для API аккаунтов: профиль и «мои грузы» с проекцией.

Проекция — та же, что у публичного груза: `build_db_plan` (как в `DbShipmentSource`)
и `project_shipment`, который считает и блок «Груз», и санкции.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import OrgKind, Role, ShipmentEventRow, ShipmentRow, User
from app.db.repositories.accounts import AccountsRepository
from app.services.accounts.access import (
    Principal,
    can_manage,
    event_nodes,
    shipment_access,
    visible_shipment_ids,
)
from app.services.accounts.db_source import build_db_plan
from app.services.accounts.errors import NotFound
from app.services.accounts.shipments import load_shipment
from app.services.tracking import Shipment, project_shipment

LOCALES = frozenset({"ru", "en"})
NAME_MAX = 256


@dataclass(frozen=True)
class MembershipInfo:
    org_id: int
    org_name: str
    org_kind: OrgKind
    role: Role
    node_codes: list[str]


@dataclass(frozen=True)
class Profile:
    user: User
    memberships: list[MembershipInfo]


@dataclass(frozen=True)
class MyShipmentView:
    shipment: Shipment
    org_id: int
    can_manage: bool
    event_nodes: list[str]  # в порядке маршрута
    container_no: str | None


class ProfileService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, user_id: int) -> Profile:
        async with self._sf() as session:
            return await self._profile(session, user_id)

    async def update(
        self, user_id: int, *, name: str | None = None, locale: str | None = None
    ) -> Profile:
        """Меняет только переданные поля; пустое имя — сброс."""
        if locale is not None and locale not in LOCALES:
            raise ValueError("bad_locale")
        if name is not None and len(name.strip()) > NAME_MAX:
            raise ValueError("name_too_long")
        async with self._sf() as session:
            user = await AccountsRepository(session).get_user(user_id)
            if user is None:
                raise NotFound
            if name is not None:
                user.name = name.strip() or None
            if locale is not None:
                user.locale = locale
            await session.commit()
            return await self._profile(session, user_id)

    @staticmethod
    async def _profile(session: AsyncSession, user_id: int) -> Profile:
        repo = AccountsRepository(session)
        user = await repo.get_user(user_id)
        if user is None:
            raise NotFound
        rows = await repo.memberships_with_kind(user_id)
        return Profile(
            user,
            [
                MembershipInfo(m.org_id, o.name, o.kind, m.role, list(m.node_codes or []))
                for m, o in rows
            ],
        )


async def my_shipments(
    session_factory: async_sessionmaker[AsyncSession], actor: Principal, now: datetime
) -> list[MyShipmentView]:
    """Все видимые принципалу неархивные грузы."""
    async with session_factory() as session:
        ids = await visible_shipment_ids(session, actor)
        rows = await AccountsRepository(session).shipments_by_ids(ids)
        return await _views(session, actor, rows, now)


async def my_shipment(
    session_factory: async_sessionmaker[AsyncSession], actor: Principal, ref: str, now: datetime
) -> MyShipmentView:
    """Один груз; невидимый — NotFound (архивный видят только управляющие)."""
    async with session_factory() as session:
        row, _ = await load_shipment(session, actor, ref, manage=False)
        views = await _views(session, actor, [row], now)
    if not views:
        raise NotFound
    return views[0]


async def _views(
    session: AsyncSession, actor: Principal, rows: list[ShipmentRow], now: datetime
) -> list[MyShipmentView]:
    repo = AccountsRepository(session)
    rows = [r for r in rows if r.planned_departure_at is not None and len(r.route or []) >= 2]
    events = await repo.live_events([r.id for r in rows])
    names = await repo.org_names({r.org_id for r in rows})
    by_shipment: dict[int, list[ShipmentEventRow]] = {}
    for e in events:
        by_shipment.setdefault(e.shipment_id, []).append(e)
    result = []
    for r in rows:
        access = await shipment_access(session, r)
        nodes = event_nodes(actor, access)
        plan = build_db_plan(r, names.get(r.org_id, ""), by_shipment.get(r.id, []))
        result.append(
            MyShipmentView(
                shipment=project_shipment(plan, now),
                org_id=r.org_id,
                can_manage=can_manage(actor, access),
                event_nodes=[code for code in r.route if code in nodes],
                container_no=r.container_no,
            )
        )
    return result
