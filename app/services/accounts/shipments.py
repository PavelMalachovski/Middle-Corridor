"""Грузы аккаунтов: создание, правка с историей, шаринг клиенту, архив.

Подписки здесь не создаются: получатели уведомлений считаются по доступу,
строки `subscriptions` — только персональные переопределения.
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import OrgKind, ShipmentRevision, ShipmentRow, ShipmentShare
from app.db.repositories.accounts import AccountsRepository, audit, aware
from app.services.accounts.access import (
    Principal,
    can_manage,
    can_share_with,
    can_view,
    creatable_orgs,
    shipment_access,
    visible_shipment_ids,
)
from app.services.accounts.errors import NotFound, PermissionDenied
from app.services.schedule import validate_route

log = structlog.get_logger()

REF_PREFIX = "MC"
EDITABLE = frozenset(
    {"container_no", "container_type", "cargo", "cargo_en", "planned_departure_at", "route"}
)
_CONTAINER_RE = re.compile(r"^[A-Z]{4}\d{7}$")


def _letter_values() -> dict[str, int]:
    """A=10, дальше по возрастанию, пропуская кратные 11 (ISO 6346)."""
    values: dict[str, int] = {}
    n = 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if n % 11 == 0:
            n += 1
        values[ch] = n
        n += 1
    return values


_LETTERS = _letter_values()


def normalize_container(no: str) -> str:
    return re.sub(r"\s+", "", no).upper()


def iso6346_valid(no: str) -> bool:
    """4 буквы + 6 цифр серийного номера + контрольная цифра (ISO 6346)."""
    code = normalize_container(no)
    if not _CONTAINER_RE.match(code):
        return False
    total = sum(
        (_LETTERS[ch] if ch.isalpha() else int(ch)) * 2**i for i, ch in enumerate(code[:10])
    )
    return total % 11 % 10 == int(code[10])


def _container(no: str) -> str:
    code = normalize_container(no)
    if not iso6346_valid(code):
        raise ValueError("bad_container")
    return code


def _departure(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("bad_departure")
    return value


def _route(route: list[str], shipment_id: int | None = None) -> list[str]:
    route = list(route)
    try:
        validate_route(route)
    except ValueError as exc:
        log.info("shipment_bad_route", shipment_id=shipment_id, detail=str(exc))
        raise ValueError("bad_route") from None
    return route


def _json(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _same(old: Any, new: Any) -> bool:
    if isinstance(old, datetime) and isinstance(new, datetime):
        return aware(old) == aware(new)
    return old == new


class ShipmentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime],
    ) -> None:
        self._sf = session_factory
        self._clock = clock

    async def create(  # noqa: PLR0913 — поля груза
        self,
        actor: Principal,
        *,
        org_id: int,
        container_no: str,
        container_type: str | None,
        route: list[str],
        planned_departure_at: datetime,
        cargo: str | None,
        cargo_en: str | None = None,
    ) -> ShipmentRow:
        async with self._sf() as session:
            org = await AccountsRepository(session).get_org(org_id)
        allowed = (
            org is not None and org.kind is OrgKind.forwarder
            if actor.is_platform_admin
            else org_id in creatable_orgs(actor)
        )
        if not allowed:
            raise PermissionDenied
        fields = {
            "container_no": _container(container_no),
            "container_type": container_type,
            "route": _route(route),
            "planned_departure_at": _departure(planned_departure_at),
            "cargo": cargo,
            "cargo_en": cargo_en,
        }
        now = self._clock()
        prefix = f"{REF_PREFIX}-{now.year % 100:02d}-"
        for attempt in range(2):  # гонка за номер — одна повторная попытка
            async with self._sf() as session:
                repo = AccountsRepository(session)
                row = ShipmentRow(
                    ref=prefix + f"{await self._next_number(repo, prefix):04d}",
                    org_id=org_id,
                    created_by=actor.user_id,
                    created_at=now,
                    **fields,
                )
                session.add(row)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    if attempt:
                        raise
                    continue
                await audit(
                    session,
                    "shipment.created",
                    "shipment",
                    at=now,
                    entity_id=row.id,
                    user_id=actor.user_id,
                    details={"org_id": org_id},
                )
                await session.commit()
                return row
        raise AssertionError("unreachable")

    @staticmethod
    async def _next_number(repo: AccountsRepository, prefix: str) -> int:
        numbers = [
            int(tail)
            for ref in await repo.refs_with_prefix(prefix)
            if (tail := ref[len(prefix) :]).isdigit()
        ]
        return max(numbers, default=0) + 1

    async def _load(self, session: AsyncSession, actor: Principal, ref: str, *, manage: bool):
        """Груз и доступ; невидимый — NotFound, видимый без права управлять — PermissionDenied."""
        row = await AccountsRepository(session).shipment_by_ref(ref)
        if row is None:
            raise NotFound
        access = await shipment_access(session, row)
        managing = can_manage(actor, access)
        if not can_view(actor, access) or (row.archived_at is not None and not managing):
            raise NotFound
        if manage and not managing:
            raise PermissionDenied
        return row, access

    async def get(self, actor: Principal, ref: str) -> ShipmentRow:
        async with self._sf() as session:
            row, _ = await self._load(session, actor, ref, manage=False)
            return row

    async def list_for(self, actor: Principal) -> list[ShipmentRow]:
        async with self._sf() as session:
            ids = await visible_shipment_ids(session, actor)
            return await AccountsRepository(session).shipments_by_ids(ids)

    async def update(self, actor: Principal, ref: str, **changes: Any) -> tuple[ShipmentRow, bool]:
        unknown = set(changes) - EDITABLE
        if unknown:
            raise ValueError("unknown_field")
        async with self._sf() as session:
            row, _ = await self._load(session, actor, ref, manage=True)
            if row.archived_at is not None:
                raise ValueError("archived")
            new = dict(changes)
            if "container_no" in new:
                new["container_no"] = _container(new["container_no"])
            if "planned_departure_at" in new:
                new["planned_departure_at"] = _departure(new["planned_departure_at"])
            if "route" in new:
                new["route"] = await self._checked_route(session, row, new["route"])
            changed = sorted(k for k, v in new.items() if not _same(getattr(row, k), v))
            if not changed:
                return row, False
            before = {k: _json(getattr(row, k)) for k in changed}
            for k in changed:
                setattr(row, k, new[k])
            now = self._clock()
            session.add(
                ShipmentRevision(
                    shipment_id=row.id,
                    changed_by=actor.user_id,
                    at=now,
                    before=before,
                    after={k: _json(new[k]) for k in changed},
                )
            )
            await audit(
                session,
                "shipment.updated",
                "shipment",
                at=now,
                entity_id=row.id,
                user_id=actor.user_id,
                details={"fields": changed},
            )
            await session.commit()
            return row, "route" in changed

    @staticmethod
    async def _checked_route(session: AsyncSession, row: ShipmentRow, route: list[str]):
        """Пройденная часть (до последнего узла с живым событием) не меняется."""
        old = list(row.route or [])
        events = await AccountsRepository(session).live_events([row.id])
        passed = max((old.index(e.node_code) for e in events if e.node_code in old), default=-1)
        route = list(route)
        if route[: passed + 1] != old[: passed + 1]:
            raise ValueError("route_passed_part")
        return _route(route, row.id)

    async def share(self, actor: Principal, ref: str, client_org_id: int) -> None:
        async with self._sf() as session:
            row, access = await self._load(session, actor, ref, manage=True)
            if row.archived_at is not None:
                raise ValueError("archived")
            repo = AccountsRepository(session)
            linked = await repo.linked_client_ids(row.org_id)
            if not can_share_with(actor, access, client_org_id, linked):
                raise PermissionDenied
            if await repo.share_exists(row.id, client_org_id):
                return
            session.add(ShipmentShare(shipment_id=row.id, org_id=client_org_id))
            await audit(
                session,
                "shipment.shared",
                "shipment",
                at=self._clock(),
                entity_id=row.id,
                user_id=actor.user_id,
                details={"org_id": client_org_id},
            )
            await session.commit()

    async def archive(self, actor: Principal, ref: str) -> ShipmentRow:
        async with self._sf() as session:
            row, _ = await self._load(session, actor, ref, manage=True)
            if row.archived_at is not None:
                return row
            now = self._clock()
            row.archived_at = now
            await audit(
                session,
                "shipment.archived",
                "shipment",
                at=now,
                entity_id=row.id,
                user_id=actor.user_id,
            )
            await session.commit()
            return row
