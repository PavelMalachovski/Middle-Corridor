"""Компании, связи экспедитор–клиент, приглашения и команда."""

from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Invitation, Membership, Organization, OrgKind, OrgLink, Role, User
from app.db.repositories.accounts import AccountsRepository, audit
from app.services import corridor
from app.services.accounts import security
from app.services.accounts.access import Principal, can_invite
from app.services.accounts.errors import NotFound, PermissionDenied
from app.services.accounts.mail import EmailSender, render

INVITATION_TTL = timedelta(days=7)


def _is_platform(actor: Principal | None) -> bool:
    """actor=None — команда админа из CLI, это тоже платформа."""
    return actor is None or actor.is_platform_admin


def _actor_id(actor: Principal | None) -> int | None:
    return None if actor is None else actor.user_id


class OrgService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mail: EmailSender,
        clock: Callable[[], datetime],
    ) -> None:
        self._sf = session_factory
        self._mail = mail
        self._clock = clock

    async def create_org(self, actor: Principal | None, name: str, kind: OrgKind) -> Organization:
        if not _is_platform(actor):
            raise PermissionDenied
        name = name.strip()
        if not name:
            raise ValueError("empty_name")
        async with self._sf() as session:
            org = Organization(name=name, kind=kind)
            session.add(org)
            await session.flush()
            await audit(
                session,
                "org.created",
                "organization",
                at=self._clock(),
                entity_id=org.id,
                user_id=_actor_id(actor),
                details={"kind": kind.value},
            )
            await session.commit()
            return org

    async def link(self, actor: Principal | None, forwarder_id: int, client_id: int) -> None:
        if not _is_platform(actor):
            raise PermissionDenied
        async with self._sf() as session:
            repo = AccountsRepository(session)
            forwarder = await repo.get_org(forwarder_id)
            client = await repo.get_org(client_id)
            if forwarder is None or client is None:
                raise NotFound
            if forwarder.kind is not OrgKind.forwarder or client.kind is not OrgKind.client:
                raise ValueError("link_kinds")
            if await repo.link_exists(forwarder_id, client_id):
                return
            repo.add(OrgLink(forwarder_id=forwarder_id, client_id=client_id))
            await audit(
                session,
                "org.linked",
                "organization",
                at=self._clock(),
                entity_id=forwarder_id,
                user_id=_actor_id(actor),
                details={"client_id": client_id},
            )
            await session.commit()

    async def invite(
        self,
        actor: Principal | None,
        org_id: int,
        email: str,
        role: Role,
        node_codes: list[str],
    ) -> Invitation:
        if not _is_platform(actor) and not (actor and can_invite(actor, org_id)):
            raise PermissionDenied
        if role is Role.owner and not _is_platform(actor):
            raise PermissionDenied
        email = security.normalize_email(email)
        nodes = list(dict.fromkeys(node_codes))
        if any(code not in corridor.NODES for code in nodes):
            raise ValueError("unknown_node")
        if nodes and role is not Role.agent:
            raise ValueError("nodes_for_agent_only")
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            org = await repo.get_org(org_id)
            if org is None:
                raise NotFound
            for old in await repo.pending_invitations(org_id, email=email, now=now):
                old.revoked_at = now
            inv = Invitation(
                org_id=org_id,
                email=email,
                role=role,
                node_codes=nodes,
                invited_by=_actor_id(actor),
                expires_at=now + INVITATION_TTL,
            )
            repo.add(inv)
            await session.flush()
            await audit(
                session,
                "invitation.created",
                "invitation",
                at=now,
                entity_id=inv.id,
                user_id=_actor_id(actor),
                details={
                    "org_id": org_id,
                    "role": role.value,
                    "nodes": nodes,
                    "email_hash": security.email_fingerprint(email),
                },
            )
            inviter = await repo.get_user(actor.user_id) if actor else None
            await session.commit()
            org_name = org.name
            locale = None
            inviter_name = (inviter.name or "Middle Corridor") if inviter else "Middle Corridor"
        subject, body = render("invited", locale, inviter=inviter_name, org=org_name)
        await self._mail.send(email, subject, body)
        return inv

    async def revoke_membership(self, actor: Principal | None, org_id: int, user_id: int) -> None:
        if not _is_platform(actor) and not (actor and can_invite(actor, org_id)):
            raise PermissionDenied
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            rows = await repo.org_memberships(org_id)
            target = next((m for m in rows if m.user_id == user_id), None)
            if target is None:
                raise NotFound
            if target.role is Role.owner and not _is_platform(actor):
                raise PermissionDenied
            if target.role is Role.owner and sum(m.role is Role.owner for m in rows) == 1:
                raise ValueError("last_owner")
            user = await repo.get_user(user_id)
            await session.delete(target)
            if user is not None:
                for inv in await repo.pending_invitations(org_id, email=user.email, now=now):
                    inv.revoked_at = now
            await audit(
                session,
                "membership.revoked",
                "membership",
                at=now,
                entity_id=target.id,
                user_id=_actor_id(actor),
                details={"org_id": org_id, "user_id": user_id},
            )
            await session.commit()

    async def members(self, actor: Principal | None, org_id: int) -> list[Membership]:
        if not _is_platform(actor) and not (actor and can_invite(actor, org_id)):
            raise PermissionDenied
        async with self._sf() as session:
            return await AccountsRepository(session).org_memberships(org_id)

    async def linked_clients(
        self, actor: Principal | None, forwarder_id: int
    ) -> list[Organization]:
        if not _is_platform(actor) and not (actor and can_invite(actor, forwarder_id)):
            raise PermissionDenied
        async with self._sf() as session:
            return await AccountsRepository(session).linked_clients(forwarder_id)

    async def set_platform_admin(self, email: str) -> User:
        email = security.normalize_email(email)
        async with self._sf() as session:
            repo = AccountsRepository(session)
            user = await repo.get_user_by_email(email)
            if user is None:
                user = User(email=email)
                repo.add(user)
            user.is_platform_admin = True
            await session.flush()
            await audit(
                session,
                "user.platform_admin",
                "user",
                at=self._clock(),
                entity_id=user.id,
                details={"email_hash": security.email_fingerprint(email)},
            )
            await session.commit()
            return user

    async def disable_user(self, email: str) -> None:
        email = security.normalize_email(email)
        now = self._clock()
        async with self._sf() as session:
            repo = AccountsRepository(session)
            user = await repo.get_user_by_email(email)
            if user is None:
                raise NotFound
            user.disabled_at = now
            await repo.revoke_user_sessions(user.id, now)
            await audit(
                session,
                "user.disabled",
                "user",
                at=now,
                entity_id=user.id,
                details={"email_hash": security.email_fingerprint(email)},
            )
            await session.commit()
