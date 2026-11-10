"""Вход по коду из письма: запрос кода, проверка, сессии, лимиты."""

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import AuthSession, Membership, User
from app.db.repositories.accounts import AccountsRepository, audit, aware
from app.services.accounts import security
from app.services.accounts.mail import EmailSender, render

log = structlog.get_logger()

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
SESSION_TTL = timedelta(days=60)
TOUCH_INTERVAL = timedelta(minutes=5)
EMAIL_LIMIT = (3, timedelta(minutes=15))
IP_LIMIT = (20, timedelta(hours=1))


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        mail: EmailSender,
        clock: Callable[[], datetime],
    ) -> None:
        self._sf = session_factory
        self._settings = settings
        self._mail = mail
        self._clock = clock

    async def request_code(self, email: str, ip: str) -> None:
        """Всегда тихо: письмо уходит только известному адресу и в пределах лимитов."""
        try:
            email = security.normalize_email(email)
        except ValueError:
            return
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            if (
                await repo.count_codes(since=now - EMAIL_LIMIT[1], email=email) >= EMAIL_LIMIT[0]
                or await repo.count_codes(since=now - IP_LIMIT[1], ip=ip) >= IP_LIMIT[0]
            ):
                return
            user = await repo.get_user_by_email(email)
            known = user is not None and user.disabled_at is None
            invited = user is None and bool(await repo.active_invitations(email, now))
            code = security.new_code()
            # Для неизвестного адреса строка нужна лишь для счётчика IP; код не используем.
            repo.add_code(
                email,
                ip,
                security.hash_code(self._settings.auth_secret, email, code),
                now,
                CODE_TTL,
            )
            send = known or invited
            locale = user.locale if user else None
            await audit(
                session,
                "login.code_sent",
                "login",
                at=now,
                user_id=user.id if user else None,
                ip=ip,
                details={"sent": send, "email_hash": security.email_fingerprint(email)},
            )
            await session.commit()
        if send:
            subject, body = render("login_code", locale, code=code)
            try:
                await self._mail.send(email, subject, body)
            except Exception:
                log.warning("login_mail_failed", email_hash=security.email_fingerprint(email))

    async def verify(
        self, email: str, code: str, device_name: str, ip: str
    ) -> tuple[str, User] | None:
        try:
            email = security.normalize_email(email)
        except ValueError:
            return None
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            row = await repo.latest_open_code(email, now)
            if row is None or not await repo.claim_attempt(row.id, MAX_ATTEMPTS):
                return None
            expected = security.hash_code(self._settings.auth_secret, email, code.strip())
            user = await repo.get_user_by_email(email)
            invitations = await repo.active_invitations(email, now)
            ok = (
                hmac.compare_digest(expected, row.code_hash)
                and (user is None or user.disabled_at is None)
                and (user is not None or invitations)
            )
            if not ok:
                await audit(
                    session,
                    "login.failed",
                    "login",
                    at=now,
                    user_id=user.id if user else None,
                    ip=ip,
                    details={"email_hash": security.email_fingerprint(email)},
                )
                await session.commit()
                return None

            if not await repo.mark_used(row.id, now):
                await session.commit()
                return None
            if user is None:
                user = User(email=email, locale="ru", created_at=now)
                repo.add(user)
                await session.flush()
            for inv in invitations:
                member = await repo.membership(user.id, inv.org_id)
                if member is None:
                    repo.add(
                        Membership(
                            user_id=user.id,
                            org_id=inv.org_id,
                            role=inv.role,
                            node_codes=list(inv.node_codes),
                            created_at=now,
                        )
                    )
                else:
                    member.role = inv.role
                    member.node_codes = list(inv.node_codes)
                inv.accepted_at = now
                await audit(
                    session,
                    "invitation.accepted",
                    "invitation",
                    at=now,
                    entity_id=inv.id,
                    user_id=user.id,
                    ip=ip,
                    details={"org_id": inv.org_id, "role": str(inv.role)},
                )
            token = security.new_token()
            repo.add(
                AuthSession(
                    user_id=user.id,
                    token_hash=security.hash_token(token),
                    last_used_at=now,
                    expires_at=now + SESSION_TTL,
                    device_name=device_name[:256] or None,
                    created_at=now,
                )
            )
            user.last_login_at = now
            await audit(
                session,
                "login.ok",
                "login",
                at=now,
                user_id=user.id,
                ip=ip,
                details={"device": device_name[:64]},
            )
            await session.commit()
            return token, user

    async def authenticate(self, token: str) -> User | None:
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            row = await repo.session_by_hash(security.hash_token(token))
            if row is None or row.revoked_at is not None or aware(row.expires_at) <= now:
                return None
            user = await repo.get_user(row.user_id)
            if user is None or user.disabled_at is not None:
                return None
            if row.last_used_at is None or now - aware(row.last_used_at) >= TOUCH_INTERVAL:
                row.last_used_at = now
                await session.commit()
            return user

    async def logout(self, token: str) -> None:
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            row = await repo.session_by_hash(security.hash_token(token))
            if row is None or row.revoked_at is not None:
                return
            row.revoked_at = now
            await audit(session, "logout", "session", at=now, entity_id=row.id, user_id=row.user_id)
            await session.commit()
