"""Вход по коду: коды, сессии, лимиты, приглашения."""

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import (
    AuditLog,
    AuthSession,
    Invitation,
    LoginCode,
    Membership,
    Organization,
    OrgKind,
    Role,
    User,
)
from app.services.accounts.auth import AuthService
from app.services.accounts.mail import LogEmailSender, ResendEmailSender
from app.services.accounts.security import hash_token, normalize_email

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def mail() -> LogEmailSender:
    return LogEmailSender()


@pytest.fixture
def auth(
    session_factory: async_sessionmaker[AsyncSession], mail: LogEmailSender, clock: Clock
) -> AuthService:
    return AuthService(session_factory, Settings(auth_secret="s3cret"), mail, clock)


def last_code(mail: LogEmailSender) -> str:
    match = re.search(r"\b(\d{6})\b", mail.sent[-1][2])
    assert match
    return match.group(1)


async def add_user(session: AsyncSession, email: str = "a@x.kz", **kw: object) -> User:
    user = User(email=email, created_at=T0, **kw)
    session.add(user)
    await session.commit()
    return user


async def add_invitation(
    session: AsyncSession, email: str, expires: timedelta = timedelta(days=7), **kw: object
) -> Invitation:
    org = Organization(name="Fwd", kind=OrgKind.forwarder)
    session.add(org)
    await session.flush()
    inv = Invitation(
        org_id=org.id,
        email=email,
        role=Role.agent,
        node_codes=["aktau"],
        expires_at=T0 + expires,
        created_at=T0,
        **kw,
    )
    session.add(inv)
    await session.commit()
    return inv


async def login(auth: AuthService, mail: LogEmailSender, email: str = "a@x.kz") -> str:
    await auth.request_code(email, "1.1.1.1")
    result = await auth.verify(email, last_code(mail), "iPhone", "1.1.1.1")
    assert result is not None
    return result[0]


async def test_unknown_email_gets_no_mail_but_same_result(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    assert await auth.request_code("nobody@x.kz", "1.1.1.1") is None
    assert mail.sent == []
    # строка осталась — чтобы лимит по IP покрывал перебор адресов
    assert len((await session.execute(select(LoginCode))).scalars().all()) == 1
    assert await auth.verify("nobody@x.kz", "000000", "d", "1.1.1.1") is None


async def test_code_flow_issues_token_once(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    await add_user(session)
    await auth.request_code("a@x.kz", "1.1.1.1")
    code = last_code(mail)
    result = await auth.verify("a@x.kz", code, "iPhone", "1.1.1.1")
    assert result is not None
    token, user = result
    row = (await session.execute(select(AuthSession))).scalar_one()
    assert row.token_hash == hash_token(token) != token
    assert user.last_login_at is not None
    # код одноразовый
    assert await auth.verify("a@x.kz", code, "iPhone", "1.1.1.1") is None
    authed = await auth.authenticate(token)
    assert authed is not None and authed.id == user.id
    await auth.request_code("a@x.kz", "1.1.1.1")
    wrong = "000000" if last_code(mail) != "000000" else "111111"
    assert await auth.verify("a@x.kz", wrong, "iPhone", "1.1.1.1") is None
    actions = {a.action for a in (await session.execute(select(AuditLog))).scalars()}
    assert {"login.code_sent", "login.ok", "login.failed"} <= actions


async def test_code_expires_after_10_min(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    await add_user(session)
    await auth.request_code("a@x.kz", "1.1.1.1")
    clock.advance(minutes=10, seconds=1)
    assert await auth.verify("a@x.kz", last_code(mail), "d", "1.1.1.1") is None


async def test_five_wrong_attempts_burn_code(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    await add_user(session)
    await auth.request_code("a@x.kz", "1.1.1.1")
    good = last_code(mail)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert await auth.verify("a@x.kz", bad, "d", "1.1.1.1") is None
    assert await auth.verify("a@x.kz", good, "d", "1.1.1.1") is None


async def test_rate_limit_email_3_per_15_min(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    await add_user(session)
    for _ in range(4):
        await auth.request_code("a@x.kz", "1.1.1.1")
    assert len(mail.sent) == 3
    clock.advance(minutes=15, seconds=1)
    await auth.request_code("a@x.kz", "1.1.1.1")
    assert len(mail.sent) == 4


async def test_rate_limit_ip_20_per_hour(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    for i in range(21):
        await add_user(session, f"u{i}@x.kz")
        await auth.request_code(f"u{i}@x.kz", "9.9.9.9")
    assert len(mail.sent) == 20
    await auth.request_code("u0@x.kz", "8.8.8.8")  # другой IP, у u0 всего одно письмо
    assert len(mail.sent) == 21
    clock.advance(hours=1, seconds=1)
    await auth.request_code("u20@x.kz", "9.9.9.9")
    assert len(mail.sent) == 22


async def test_invitation_accepted_on_verify_creates_user_and_membership(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    inv = await add_invitation(session, "new@x.kz")
    await auth.request_code("New@X.kz ", "1.1.1.1")
    assert len(mail.sent) == 1
    result = await auth.verify("new@x.kz", last_code(mail), "d", "1.1.1.1")
    assert result is not None
    user = result[1]
    member = (await session.execute(select(Membership))).scalar_one()
    assert (member.user_id, member.org_id, member.role) == (user.id, inv.org_id, Role.agent)
    assert member.node_codes == ["aktau"]
    await session.refresh(inv)
    assert inv.accepted_at is not None
    actions = [a.action for a in (await session.execute(select(AuditLog))).scalars()]
    assert "invitation.accepted" in actions


async def test_invitation_updates_existing_membership(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    user = await add_user(session)
    inv = await add_invitation(session, "a@x.kz")
    session.add(Membership(user_id=user.id, org_id=inv.org_id, role=Role.viewer, node_codes=[]))
    await session.commit()
    await login(auth, mail)
    member = (await session.execute(select(Membership))).scalar_one()
    await session.refresh(member)
    assert member.role == Role.agent and member.node_codes == ["aktau"]


async def test_expired_or_revoked_invitation_ignored(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    await add_invitation(session, "old@x.kz", expires=timedelta(days=-1))
    await add_invitation(session, "rev@x.kz", revoked_at=T0)
    await auth.request_code("old@x.kz", "1.1.1.1")
    await auth.request_code("rev@x.kz", "1.1.1.1")
    assert mail.sent == []
    # приглашение истекло уже после отправки кода — вход тоже не проходит
    await add_invitation(session, "late@x.kz", expires=timedelta(minutes=5))
    await auth.request_code("late@x.kz", "1.1.1.1")
    clock.advance(minutes=6)
    assert await auth.verify("late@x.kz", last_code(mail), "d", "1.1.1.1") is None
    assert (await session.execute(select(User))).scalars().all() == []


async def test_logout_revokes(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    await add_user(session)
    token = await login(auth, mail)
    assert await auth.authenticate(token) is not None
    await auth.logout(token)
    assert await auth.authenticate(token) is None
    await auth.logout(token)  # повторный выход безвреден


async def test_session_expires_60_days(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    await add_user(session)
    token = await login(auth, mail)
    # скользящее last_used_at не продлевает жёсткий срок
    for _ in range(5):
        clock.advance(days=11)
        assert await auth.authenticate(token) is not None
    clock.advance(days=5, seconds=1)
    assert await auth.authenticate(token) is None


async def test_last_used_touched_at_most_every_5_min(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession, clock: Clock
) -> None:
    await add_user(session)
    token = await login(auth, mail)
    clock.advance(minutes=2)
    await auth.authenticate(token)
    row = (await session.execute(select(AuthSession))).scalar_one()
    await session.refresh(row)
    assert row.last_used_at is not None and row.last_used_at.replace(tzinfo=UTC) == T0
    clock.advance(minutes=4)
    await auth.authenticate(token)
    await session.refresh(row)
    assert row.last_used_at.replace(tzinfo=UTC) == clock.now


async def test_disabled_user_cannot_login_or_authenticate(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    user = await add_user(session)
    token = await login(auth, mail)
    user.disabled_at = T0
    await session.commit()
    assert await auth.authenticate(token) is None
    mail.sent.clear()
    await auth.request_code("a@x.kz", "2.2.2.2")
    assert mail.sent == []
    assert await auth.verify("a@x.kz", "123456", "d", "2.2.2.2") is None


async def test_disabled_after_code_sent_cannot_verify(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    user = await add_user(session)
    await auth.request_code("a@x.kz", "1.1.1.1")
    user.disabled_at = T0
    await session.commit()
    assert await auth.verify("a@x.kz", last_code(mail), "d", "1.1.1.1") is None


async def test_email_normalized_everywhere(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    assert normalize_email("  A@X.KZ ") == "a@x.kz"
    with pytest.raises(ValueError):
        normalize_email("nope")
    await add_user(session, "a@x.kz")
    await auth.request_code("  A@X.kz", "1.1.1.1")
    assert len(mail.sent) == 1 and mail.sent[0][0] == "a@x.kz"
    assert await auth.verify(" A@x.KZ ", last_code(mail), "d", "1.1.1.1") is not None
    assert (await session.execute(select(LoginCode.email))).scalars().all() == ["a@x.kz"]
    assert await auth.request_code("not-an-email", "1.1.1.1") is None


async def test_mail_log_has_no_code(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    await add_user(session)
    with structlog.testing.capture_logs() as logs:
        await auth.request_code("a@x.kz", "1.1.1.1")
        await auth.verify("a@x.kz", last_code(mail), "d", "1.1.1.1")
    dump = json.dumps(logs, default=str)
    assert last_code(mail) not in dump and "a@x.kz" not in dump
    assert any(entry["event"] == "mail_sent" for entry in logs)
    details = [a.details for a in (await session.execute(select(AuditLog))).scalars()]
    assert "a@x.kz" not in json.dumps(details) and last_code(mail) not in json.dumps(details)


async def test_resend_sender_posts_expected_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ResendEmailSender("key123", "MC <no-reply@mc.kz>", client).send(
            "a@x.kz", "Subj", "Body"
        )
    (req,) = seen
    assert str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == "Bearer key123"
    assert json.loads(req.content) == {
        "from": "MC <no-reply@mc.kz>",
        "to": ["a@x.kz"],
        "subject": "Subj",
        "text": "Body",
    }


async def test_attempt_claim_is_capped_and_mark_used_once(
    session: AsyncSession,
) -> None:
    from app.db.repositories.accounts import AccountsRepository

    repo = AccountsRepository(session)
    row = repo.add_code("a@x.kz", "1.1.1.1", "h", T0, timedelta(minutes=10))
    await session.commit()
    results = [await repo.claim_attempt(row.id, 5) for _ in range(7)]
    assert results == [True] * 5 + [False] * 2
    other = repo.add_code("b@x.kz", "1.1.1.1", "h", T0, timedelta(minutes=10))
    await session.commit()
    assert await repo.mark_used(other.id, T0) is True
    assert await repo.mark_used(other.id, T0) is False
    assert await repo.claim_attempt(other.id, 5) is False


async def test_parallel_verify_yields_single_session(
    auth: AuthService, mail: LogEmailSender, session: AsyncSession
) -> None:
    import asyncio

    await add_user(session)
    await auth.request_code("a@x.kz", "1.1.1.1")
    code = last_code(mail)
    results = await asyncio.gather(*[auth.verify("a@x.kz", code, "d", "1.1.1.1") for _ in range(5)])
    assert len([r for r in results if r is not None]) == 1
    assert len((await session.execute(select(AuthSession))).scalars().all()) == 1


class FailingSender:
    async def send(self, to: str, subject: str, text: str) -> None:
        raise RuntimeError("smtp down")


async def test_request_code_swallows_mail_errors(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession, clock: Clock
) -> None:
    await add_user(session)
    svc = AuthService(session_factory, Settings(auth_secret="s3cret"), FailingSender(), clock)
    with structlog.testing.capture_logs() as logs:
        assert await svc.request_code("a@x.kz", "1.1.1.1") is None
    assert len((await session.execute(select(LoginCode))).scalars().all()) == 1
    assert "a@x.kz" not in json.dumps(logs, default=str)
