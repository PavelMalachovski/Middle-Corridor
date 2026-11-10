"""Доступ к данным аккаунтов: коды входа, сессии, приглашения, аудит."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    AuthSession,
    Invitation,
    LoginCode,
    Membership,
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
