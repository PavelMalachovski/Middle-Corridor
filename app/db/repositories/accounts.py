"""Доступ к данным аккаунтов: коды входа, сессии, приглашения, аудит."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    AuthSession,
    Device,
    Invitation,
    LoginCode,
    Membership,
    Organization,
    OrgLink,
    ShipmentEventRow,
    ShipmentRow,
    ShipmentShare,
    Subscription,
    User,
)


def aware(value: datetime) -> datetime:
    """SQLite отдаёт наивные даты — считаем их UTC (в Postgres уже с поясом)."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def audit(
    session: AsyncSession,
    action: str,
    entity: str,
    *,
    at: datetime,
    entity_id: str | int | None = None,
    user_id: int | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            at=at,
            ip=ip,
            details=details or {},
        )
    )


class AccountsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def active_invitations(self, email: str, now: datetime) -> list[Invitation]:
        result = await self._session.execute(
            select(Invitation)
            .where(
                Invitation.email == email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.id)
        )
        return [i for i in result.scalars() if aware(i.expires_at) > now]

    async def count_codes(
        self, *, since: datetime, email: str | None = None, ip: str | None = None
    ) -> int:
        stmt = select(func.count(LoginCode.id)).where(LoginCode.created_at > since)
        if email is not None:
            stmt = stmt.where(LoginCode.email == email)
        if ip is not None:
            stmt = stmt.where(LoginCode.ip == ip)
        return (await self._session.execute(stmt)).scalar_one()

    def add_code(
        self, email: str, ip: str, code_hash: str, now: datetime, ttl: timedelta
    ) -> LoginCode:
        row = LoginCode(
            email=email,
            ip=ip,
            code_hash=code_hash,
            expires_at=now + ttl,
            attempts=0,
            created_at=now,
        )
        self._session.add(row)
        return row

    async def latest_open_code(self, email: str, now: datetime) -> LoginCode | None:
        result = await self._session.execute(
            select(LoginCode)
            .where(LoginCode.email == email, LoginCode.used_at.is_(None))
            .order_by(LoginCode.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None or aware(row.expires_at) <= now:
            return None
        return row

    async def claim_attempt(self, code_id: int, max_attempts: int) -> bool:
        """Атомарно занять попытку: счётчик растёт в SQL, гонки не дают лишних."""
        result = await self._session.execute(
            update(LoginCode)
            .where(
                LoginCode.id == code_id,
                LoginCode.used_at.is_(None),
                LoginCode.attempts < max_attempts,
            )
            .values(attempts=LoginCode.attempts + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def mark_used(self, code_id: int, now: datetime) -> bool:
        """Погасить код условным UPDATE: сессию получит только победитель."""
        result = await self._session.execute(
            update(LoginCode)
            .where(LoginCode.id == code_id, LoginCode.used_at.is_(None))
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def membership(self, user_id: int, org_id: int) -> Membership | None:
        result = await self._session.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.org_id == org_id)
        )
        return result.scalar_one_or_none()

    def add(self, row: object) -> None:
        self._session.add(row)

    async def session_by_hash(self, token_hash: str) -> AuthSession | None:
        result = await self._session.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_user(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def memberships_with_kind(self, user_id: int) -> list[tuple[Membership, Organization]]:
        result = await self._session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.id)
        )
        return [(m, o) for m, o in result.all()]

    async def shared_org_ids(self, shipment_id: int) -> frozenset[int]:
        result = await self._session.execute(
            select(ShipmentShare.org_id).where(ShipmentShare.shipment_id == shipment_id)
        )
        return frozenset(result.scalars())

    async def linked_client_ids(self, forwarder_id: int) -> set[int]:
        result = await self._session.execute(
            select(OrgLink.client_id).where(OrgLink.forwarder_id == forwarder_id)
        )
        return set(result.scalars())

    async def candidate_shipments(
        self, org_ids: set[int] | None
    ) -> list[tuple[int, int, list[str], bool]]:
        """Неархивные отправки: (id, org_id, route, расшарена ли одной из org_ids).

        org_ids=None — все (платформа). Иначе — свои компании и расшаренные им.
        """
        base = select(ShipmentRow.id, ShipmentRow.org_id, ShipmentRow.route).where(
            ShipmentRow.archived_at.is_(None)
        )
        if org_ids is None:
            result = await self._session.execute(base.order_by(ShipmentRow.id))
            return [(i, o, list(r or []), False) for i, o, r in result.all()]
        if not org_ids:
            return []
        shared_ids = select(ShipmentShare.shipment_id).where(ShipmentShare.org_id.in_(org_ids))
        result = await self._session.execute(
            base.add_columns(ShipmentRow.id.in_(shared_ids))
            .where(or_(ShipmentRow.org_id.in_(org_ids), ShipmentRow.id.in_(shared_ids)))
            .order_by(ShipmentRow.id)
        )
        return [(i, o, list(r or []), bool(sh)) for i, o, r, sh in result.all()]

    async def get_org(self, org_id: int) -> Organization | None:
        return await self._session.get(Organization, org_id)

    async def link_exists(self, forwarder_id: int, client_id: int) -> bool:
        result = await self._session.execute(
            select(OrgLink.client_id).where(
                OrgLink.forwarder_id == forwarder_id, OrgLink.client_id == client_id
            )
        )
        return result.first() is not None

    async def linked_clients(self, forwarder_id: int) -> list[Organization]:
        result = await self._session.execute(
            select(Organization)
            .join(OrgLink, OrgLink.client_id == Organization.id)
            .where(OrgLink.forwarder_id == forwarder_id)
            .order_by(Organization.id)
        )
        return list(result.scalars())

    async def org_memberships(self, org_id: int) -> list[Membership]:
        result = await self._session.execute(
            select(Membership).where(Membership.org_id == org_id).order_by(Membership.id)
        )
        return list(result.scalars())

    async def org_members_with_users(self, org_id: int) -> list[tuple[Membership, User]]:
        result = await self._session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.org_id == org_id)
            .order_by(Membership.id)
        )
        return [(m, u) for m, u in result.all()]

    async def pending_invitations(
        self, org_id: int, *, email: str | None = None, now: datetime
    ) -> list[Invitation]:
        stmt = select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        if email is not None:
            stmt = stmt.where(Invitation.email == email)
        result = await self._session.execute(stmt.order_by(Invitation.id))
        return [i for i in result.scalars() if aware(i.expires_at) > now]

    async def revoke_user_sessions(self, user_id: int, now: datetime) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )

    async def shipment_by_ref(self, ref: str) -> ShipmentRow | None:
        result = await self._session.execute(select(ShipmentRow).where(ShipmentRow.ref == ref))
        return result.scalar_one_or_none()

    async def shipments_by_ids(self, ids: list[int]) -> list[ShipmentRow]:
        if not ids:
            return []
        result = await self._session.execute(
            select(ShipmentRow).where(ShipmentRow.id.in_(ids)).order_by(ShipmentRow.id)
        )
        return list(result.scalars())

    async def refs_with_prefix(self, prefix: str) -> list[str]:
        result = await self._session.execute(
            select(ShipmentRow.ref).where(ShipmentRow.ref.startswith(prefix, autoescape=True))
        )
        return list(result.scalars())

    async def share_exists(self, shipment_id: int, org_id: int) -> bool:
        return await self._session.get(ShipmentShare, (shipment_id, org_id)) is not None

    async def live_events(self, shipment_ids: list[int]) -> list[ShipmentEventRow]:
        """События, которые никто не исправил (на них не ссылается supersedes_id); по id."""
        if not shipment_ids:
            return []
        superseded = select(ShipmentEventRow.supersedes_id).where(
            ShipmentEventRow.supersedes_id.is_not(None)
        )
        stmt = select(ShipmentEventRow).where(
            ShipmentEventRow.shipment_id.in_(shipment_ids),
            ShipmentEventRow.id.not_in(superseded),
        )
        result = await self._session.execute(stmt.order_by(ShipmentEventRow.id))
        return list(result.scalars())

    async def all_events(self, shipment_id: int) -> list[ShipmentEventRow]:
        """Все события груза, включая исправленные; по id."""
        result = await self._session.execute(
            select(ShipmentEventRow)
            .where(ShipmentEventRow.shipment_id == shipment_id)
            .order_by(ShipmentEventRow.id)
        )
        return list(result.scalars())

    async def org_names(self, org_ids: set[int]) -> dict[int, str]:
        if not org_ids:
            return {}
        result = await self._session.execute(
            select(Organization.id, Organization.name).where(Organization.id.in_(org_ids))
        )
        return {i: n for i, n in result.all()}

    async def users_in_orgs(self, org_ids: set[int]) -> list[User]:
        """Участники любой из организаций (по одному разу)."""
        result = await self._session.execute(
            select(User)
            .where(User.id.in_(select(Membership.user_id).where(Membership.org_id.in_(org_ids))))
            .order_by(User.id)
        )
        return list(result.scalars())

    async def subscriptions_for(self, shipment_id: int) -> dict[int, Subscription]:
        result = await self._session.execute(
            select(Subscription).where(Subscription.shipment_id == shipment_id)
        )
        return {sub.user_id: sub for sub in result.scalars()}

    async def get_subscription(self, user_id: int, shipment_id: int) -> Subscription | None:
        return await self._session.get(Subscription, (user_id, shipment_id))

    async def active_devices(self, user_ids: list[int]) -> list[Device]:
        result = await self._session.execute(
            select(Device)
            .where(Device.user_id.in_(user_ids), Device.revoked_at.is_(None))
            .order_by(Device.id)
        )
        return list(result.scalars())

    async def device_by_token(self, token: str) -> Device | None:
        result = await self._session.execute(select(Device).where(Device.apns_token == token))
        return result.scalar_one_or_none()
