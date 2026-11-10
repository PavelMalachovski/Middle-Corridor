from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models import (
    AuditLog,
    Invitation,
    Membership,
    Organization,
    OrgKind,
    OrgLink,
    Role,
    User,
)
from app.services.accounts.access import MembershipView, Principal
from app.services.accounts.errors import PermissionDenied
from app.services.accounts.mail import LogEmailSender
from app.services.accounts.orgs import OrgService

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def mail() -> LogEmailSender:
    return LogEmailSender()


@pytest.fixture
def svc(session_factory, mail) -> OrgService:
    return OrgService(session_factory, mail, lambda: NOW)


def platform() -> Principal:
    return Principal(1, True, ())


def member(org: int, role: Role, kind: OrgKind = OrgKind.forwarder) -> Principal:
    return Principal(5, False, (MembershipView(org, kind, role, frozenset()),))


async def test_only_platform_creates_orgs_and_links(svc, session):
    with pytest.raises(PermissionDenied):
        await svc.create_org(member(1, Role.owner), "X", OrgKind.forwarder)
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    cli = await svc.create_org(platform(), "Cli", OrgKind.client)
    with pytest.raises(PermissionDenied):
        await svc.link(member(fwd.id, Role.owner), fwd.id, cli.id)
    await svc.link(None, fwd.id, cli.id)
    assert (await session.execute(select(OrgLink))).scalars().one().client_id == cli.id
    with pytest.raises(ValueError, match="link_kinds"):
        await svc.link(None, cli.id, fwd.id)
    actions = {a for (a,) in (await session.execute(select(AuditLog.action))).all()}
    assert {"org.created", "org.linked"} <= actions


async def test_forwarder_admin_invites_agent_with_nodes(svc, mail, session):
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    inv = await svc.invite(
        member(fwd.id, Role.admin), fwd.id, " Agent@Firm.KZ ", Role.agent, ["AKTAU", "POTI"]
    )
    assert inv.email == "agent@firm.kz"
    assert inv.node_codes == ["AKTAU", "POTI"]
    assert inv.expires_at > NOW
    assert len(mail.sent) == 1 and mail.sent[0][0] == "agent@firm.kz"
    with pytest.raises(PermissionDenied):
        await svc.invite(member(fwd.id, Role.agent), fwd.id, "a@b.kz", Role.viewer, [])
    with pytest.raises(PermissionDenied):
        await svc.invite(member(fwd.id + 1, Role.owner), fwd.id, "a@b.kz", Role.viewer, [])


async def test_unknown_node_rejected(svc):
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    with pytest.raises(ValueError, match="unknown_node"):
        await svc.invite(None, fwd.id, "a@b.kz", Role.agent, ["NOWHERE"])


async def test_owner_role_only_by_platform(svc):
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    with pytest.raises(PermissionDenied):
        await svc.invite(member(fwd.id, Role.owner), fwd.id, "a@b.kz", Role.owner, [])
    inv = await svc.invite(None, fwd.id, "a@b.kz", Role.owner, [])
    assert inv.role is Role.owner


async def test_reinvite_revokes_previous(svc, session):
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    first = await svc.invite(None, fwd.id, "a@b.kz", Role.viewer, [])
    second = await svc.invite(None, fwd.id, "A@b.kz", Role.admin, [])
    rows = {i.id: i for i in (await session.execute(select(Invitation))).scalars()}
    assert rows[first.id].revoked_at is not None
    assert rows[second.id].revoked_at is None


async def test_linked_clients_only_own(svc):
    f1 = await svc.create_org(None, "F1", OrgKind.forwarder)
    f2 = await svc.create_org(None, "F2", OrgKind.forwarder)
    c1 = await svc.create_org(None, "C1", OrgKind.client)
    c2 = await svc.create_org(None, "C2", OrgKind.client)
    await svc.link(None, f1.id, c1.id)
    await svc.link(None, f2.id, c2.id)
    got = await svc.linked_clients(member(f1.id, Role.admin), f1.id)
    assert [o.id for o in got] == [c1.id]
    with pytest.raises(PermissionDenied):
        await svc.linked_clients(member(f1.id, Role.admin), f2.id)


async def test_revoke_membership_and_last_owner(svc, session):
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    session.add_all([User(id=10, email="o@x.kz"), User(id=11, email="v@x.kz")])
    await session.flush()
    session.add_all(
        [
            Membership(user_id=10, org_id=fwd.id, role=Role.owner, node_codes=[]),
            Membership(user_id=11, org_id=fwd.id, role=Role.viewer, node_codes=[]),
        ]
    )
    await session.commit()
    with pytest.raises(ValueError, match="last_owner"):
        await svc.revoke_membership(None, fwd.id, 10)
    await svc.revoke_membership(member(fwd.id, Role.owner), fwd.id, 11)
    members = await svc.members(member(fwd.id, Role.owner), fwd.id)
    assert [m.user_id for m in members] == [10]


async def test_set_platform_admin(svc, session):
    await svc.set_platform_admin("Boss@X.kz")
    user = (await session.execute(select(User))).scalars().one()
    assert user.email == "boss@x.kz" and user.is_platform_admin
    assert (await session.execute(select(Organization))).first() is None


async def test_invite_mail_failure_keeps_invitation(session_factory, session):
    from app.services.accounts.errors import InvitationMailFailed

    class Broken(LogEmailSender):
        async def send(self, to: str, subject: str, text: str) -> None:
            raise OSError("down")

    svc = OrgService(session_factory, Broken(), lambda: NOW)
    fwd = await svc.create_org(None, "Fwd", OrgKind.forwarder)
    with pytest.raises(InvitationMailFailed) as err:
        await svc.invite(None, fwd.id, "a@x.kz", Role.viewer, [])
    inv = (await session.execute(select(Invitation))).scalars().one()
    assert err.value.invitation_id == inv.id
