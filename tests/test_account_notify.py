from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models import (
    CheckpointEventKind,
    Device,
    Membership,
    Organization,
    OrgKind,
    Role,
    ShipmentShare,
    Subscription,
    User,
)
from app.integrations.mock.fleet import ROUTE_KOSTANAY
from app.services.accounts.access import MembershipView, Principal
from app.services.accounts.errors import NotFound
from app.services.accounts.events import EventService
from app.services.accounts.mail import LogEmailSender
from app.services.accounts.notify import ShipmentNotifier, event_text
from app.services.accounts.shipments import ShipmentService

NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
DEPART = datetime(2027, 3, 1, 8, 0, tzinfo=UTC)
K = CheckpointEventKind


def _fresh(stmt):
    return stmt.execution_options(populate_existing=True)


def tok(n: int) -> str:
    return f"{n:02x}" * 32


class FakePush:
    def __init__(self, results: dict[str, list[str]] | None = None) -> None:
        self.sent: list[tuple[str, str, str, str, dict]] = []
        self.results = results or {}

    async def send(self, token, env, title, body, data):
        self.sent.append((token, env, title, body, data))
        queue = self.results.get(token)
        return queue.pop(0) if queue else "ok"


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def world(session, session_factory):
    fwd = Organization(name="Fwd", kind=OrgKind.forwarder)
    client = Organization(name="Client", kind=OrgKind.client)
    session.add_all([fwd, client])
    await session.flush()
    users = {}
    for name, org, role in [
        ("author", fwd, Role.owner),
        ("colleague", fwd, Role.admin),
        ("viewer", client, Role.viewer),
        ("muted", fwd, Role.viewer),
    ]:
        u = User(email=f"{name}@x.test", locale="en" if name == "viewer" else "ru")
        session.add(u)
        await session.flush()
        session.add(Membership(user_id=u.id, org_id=org.id, role=role, node_codes=[]))
        users[name] = u
    admin = User(email="root@x.test", is_platform_admin=True)
    session.add(admin)
    await session.flush()
    users["root"] = admin
    await session.commit()
    author = users["author"]
    ship = await ShipmentService(session_factory, lambda: NOW).create(
        Principal(
            author.id, False, (MembershipView(fwd.id, OrgKind.forwarder, Role.owner, frozenset()),)
        ),
        org_id=fwd.id,
        container_no="CSQU3054383",
        container_type=None,
        route=list(ROUTE_KOSTANAY),
        planned_departure_at=DEPART,
        cargo="СЕКРЕТНЫЙ ГРУЗ",
    )
    session.add(ShipmentShare(shipment_id=ship.id, org_id=client.id))
    for i, u in enumerate(users.values()):
        session.add(Device(user_id=u.id, apns_token=tok(i + 1), environment="sandbox"))
    session.add(Subscription(user_id=users["muted"].id, shipment_id=ship.id, muted_at=NOW))
    await session.commit()
    return {"ship": ship, "users": users, "fwd": fwd, "client": client}


def _notifier(session_factory, push=None, mail=None):
    push = push or FakePush()
    mail = mail or LogEmailSender()
    return ShipmentNotifier(session_factory, push, mail, sleep=no_sleep), push, mail


async def _fire(notifier, world, kind=K.arrived, hold=None):
    from app.db.models import ShipmentEventRow

    ev = ShipmentEventRow(
        shipment_id=world["ship"].id, kind=kind, node_code="POTI", occurred_at=NOW, hold_code=hold
    )
    await notifier.on_event(ev, world["ship"], world["users"]["author"].id)
    await notifier.drain()


def _token_of(world, name: str) -> str:
    return tok(list(world["users"]).index(name) + 1)


async def test_author_not_notified(session_factory, world):
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    tokens = {s[0] for s in push.sent}
    assert _token_of(world, "author") not in tokens
    assert "author@x.test" not in {m[0] for m in mail.sent}
    assert _token_of(world, "colleague") in tokens
    assert "colleague@x.test" in {m[0] for m in mail.sent}


async def test_only_viewers_with_access(session_factory, session, world):
    await session.execute(
        ShipmentShare.__table__.delete().where(ShipmentShare.shipment_id == world["ship"].id)
    )
    await session.commit()
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    tokens = {s[0] for s in push.sent}
    assert _token_of(world, "viewer") not in tokens
    assert "viewer@x.test" not in {m[0] for m in mail.sent}
    assert _token_of(world, "colleague") in tokens


async def test_platform_admin_and_shared_viewer(session_factory, world):
    n, push, _ = _notifier(session_factory)
    await _fire(n, world)
    tokens = {s[0] for s in push.sent}
    assert _token_of(world, "root") not in tokens
    assert _token_of(world, "viewer") in tokens


async def test_disabled_user_skipped(session_factory, session, world):
    world["users"]["colleague"].disabled_at = NOW
    session.add(world["users"]["colleague"])
    await session.commit()
    n, push, _ = _notifier(session_factory)
    await _fire(n, world)
    assert _token_of(world, "colleague") not in {s[0] for s in push.sent}


async def test_muted_skipped(session_factory, world):
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    assert _token_of(world, "muted") not in {s[0] for s in push.sent}
    assert "muted@x.test" not in {m[0] for m in mail.sent}


async def test_channel_flags(session_factory, session, world):
    session.add(
        Subscription(
            user_id=world["users"]["colleague"].id,
            shipment_id=world["ship"].id,
            push=False,
            email=True,
        )
    )
    await session.commit()
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    assert _token_of(world, "colleague") not in {s[0] for s in push.sent}
    assert "colleague@x.test" in {m[0] for m in mail.sent}


async def test_gone_token_revoked(session_factory, session, world):
    bad = _token_of(world, "colleague")
    n, push, _ = _notifier(session_factory, FakePush({bad: ["gone"]}))
    await _fire(n, world)
    assert sum(1 for s in push.sent if s[0] == bad) == 1  # gone не повторяется
    dev = (
        await session.execute(_fresh(select(Device).where(Device.apns_token == bad)))
    ).scalar_one()
    assert dev.revoked_at is not None
    n2, push2, _ = _notifier(session_factory)
    await _fire(n2, world)
    assert bad not in {s[0] for s in push2.sent}


async def test_error_retried_once(session_factory, world):
    t = _token_of(world, "colleague")
    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    push = FakePush({t: ["error", "ok"]})
    n = ShipmentNotifier(session_factory, push, LogEmailSender(), sleep=sleep)
    await _fire(n, world)
    assert sum(1 for s in push.sent if s[0] == t) == 2
    assert sleeps and sleeps[0] == 30

    push2 = FakePush({t: ["error", "error", "ok"]})
    n2 = ShipmentNotifier(session_factory, push2, LogEmailSender(), sleep=no_sleep)
    await _fire(n2, world)
    assert sum(1 for s in push2.sent if s[0] == t) == 2


async def test_failures_do_not_raise_and_others_still_get(session_factory, world):
    class Boom(LogEmailSender):
        async def send(self, to, subject, text):
            raise RuntimeError("smtp down")

    n, push, _ = _notifier(session_factory, mail=Boom())
    await _fire(n, world)
    assert push.sent


async def test_on_event_returns_before_delivery(session_factory, world):
    n, push, _ = _notifier(session_factory)
    from app.db.models import ShipmentEventRow

    ev = ShipmentEventRow(
        shipment_id=world["ship"].id, kind=K.arrived, node_code="POTI", occurred_at=NOW
    )
    await n.on_event(ev, world["ship"], world["users"]["author"].id)
    assert push.sent == []
    await n.drain()
    assert push.sent


async def test_push_body_has_no_cargo_or_sanctions(session_factory, world):
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    blobs = [repr(s) for s in push.sent] + [repr(m) for m in mail.sent]
    for blob in blobs:
        for forbidden in ("СЕКРЕТНЫЙ", "CSQU", "sanction", "санкц", "Client", "Fwd"):
            assert forbidden not in blob
    ref = world["ship"].ref
    assert all(s[2] == ref and s[4] == {"ref": ref} for s in push.sent)


async def test_text_follows_user_locale_and_email_template(session_factory, world):
    n, push, mail = _notifier(session_factory)
    await _fire(n, world)
    ref = world["ship"].ref
    by_token = {s[0]: s[3] for s in push.sent}
    assert by_token[_token_of(world, "colleague")] == f"{ref}: прибыл в Поти"
    assert by_token[_token_of(world, "viewer")] == f"{ref}: arrived at Poti"
    ru = next(m for m in mail.sent if m[0] == "colleague@x.test")
    assert ru[1] == f"{ref}: прибыл в Поти"
    assert ru[2].endswith("Подробности — в приложении Middle Corridor.")
    en = next(m for m in mail.sent if m[0] == "viewer@x.test")
    assert en[2].endswith("Details are in the Middle Corridor app.")


async def test_route_changed(session_factory, world):
    n, push, _ = _notifier(session_factory)
    await n.on_route_changed(world["ship"], world["users"]["author"].id)
    await n.drain()
    ref = world["ship"].ref
    bodies = {s[3] for s in push.sent}
    assert bodies == {f"{ref}: изменён маршрут", f"{ref}: route changed"}


async def test_event_service_hook_wires_notifier(session_factory, world):
    n, push, _ = _notifier(session_factory)
    svc = EventService(session_factory, lambda: NOW, on_event=n.on_event)
    fwd = world["fwd"]
    actor = Principal(
        world["users"]["author"].id,
        False,
        (MembershipView(fwd.id, OrgKind.forwarder, Role.owner, frozenset()),),
    )
    await svc.add(actor, world["ship"].ref, kind=K.arrived, node_code=ROUTE_KOSTANAY[0])
    await n.drain()
    assert push.sent


def test_event_text_ru_en():
    r = "MC-1"
    assert event_text(r, K.arrived, "POTI", None, "ru") == "MC-1: прибыл в Поти"
    assert event_text(r, K.departed, "POTI", None, "ru") == "MC-1: убыл из Поти"
    assert (
        event_text(r, K.held, "POTI", "weather_ban", "ru") == "MC-1: стоит в Поти — погодный запрет"
    )
    assert event_text(r, K.held, "POTI", "customs_wait", "ru") == "MC-1: стоит в Поти — таможня"
    assert (
        event_text(r, K.held, "POTI", "ferry_loading_wait", "ru")
        == "MC-1: стоит в Поти — ожидание парома"
    )
    assert event_text(r, K.held, "POTI", "other", "ru") == "MC-1: стоит в Поти"
    assert event_text(r, K.held, "POTI", None, "ru") == "MC-1: стоит в Поти"
    assert event_text(r, K.released, "POTI", None, "ru") == "MC-1: снят со стоянки в Поти"
    assert event_text(r, K.arrived, "POTI", None, "en") == "MC-1: arrived at Poti"
    assert event_text(r, K.departed, "POTI", None, "en") == "MC-1: departed Poti"
    assert event_text(r, K.held, "POTI", "weather_ban", "en") == "MC-1: held at Poti — weather ban"
    assert event_text(r, K.held, "POTI", "customs_wait", "en") == "MC-1: held at Poti — customs"
    assert (
        event_text(r, K.held, "POTI", "ferry_loading_wait", "en")
        == "MC-1: held at Poti — waiting for ferry"
    )
    assert event_text(r, K.held, "POTI", "other", "en") == "MC-1: held at Poti"
    assert event_text(r, K.released, "POTI", None, "en") == "MC-1: released at Poti"
    assert event_text(r, K.arrived, "POTI", None, "de") == "MC-1: прибыл в Поти"


async def test_register_device(session_factory, session, world):
    n, _, _ = _notifier(session_factory)
    a, b = world["users"]["colleague"].id, world["users"]["viewer"].id
    t = "cd" * 40
    await n.register_device(a, t, "sandbox")
    await n.register_device(b, t, "production")
    rows = (
        (await session.execute(_fresh(select(Device).where(Device.apns_token == t))))
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].user_id == b and rows[0].environment == "production"
    rows[0].revoked_at = NOW
    await session.commit()
    await n.register_device(b, t, "production")
    row = (await session.execute(_fresh(select(Device).where(Device.apns_token == t)))).scalar_one()
    assert row.revoked_at is None


@pytest.mark.parametrize(
    ("token", "env", "err"),
    [
        ("ab" * 40, "dev", "bad_environment"),
        ("zz" * 40, "sandbox", "bad_token"),
        ("ab" * 10, "sandbox", "bad_token"),
        ("ab" * 101, "sandbox", "bad_token"),
    ],
)
async def test_register_device_validation(session_factory, world, token, env, err):
    n, _, _ = _notifier(session_factory)
    with pytest.raises(ValueError, match=err):
        await n.register_device(world["users"]["viewer"].id, token, env)


async def test_set_subscription(session_factory, session, world):
    n, push, _ = _notifier(session_factory)
    fwd, client = world["fwd"], world["client"]
    viewer = Principal(
        world["users"]["viewer"].id,
        False,
        (MembershipView(client.id, OrgKind.client, Role.viewer, frozenset()),),
    )
    ref = world["ship"].ref
    await n.set_subscription(viewer, ref, push=False, email=True, muted=False)
    await n.set_subscription(viewer, ref, push=False, email=False, muted=True)
    sub = (
        await session.execute(
            _fresh(select(Subscription).where(Subscription.user_id == viewer.user_id))
        )
    ).scalar_one()
    assert (sub.push, sub.email, sub.muted_at is not None) == (False, False, True)
    await n.set_subscription(viewer, ref, push=True, email=True, muted=False)
    sub = (
        await session.execute(
            _fresh(select(Subscription).where(Subscription.user_id == viewer.user_id))
        )
    ).scalar_one()
    assert sub.muted_at is None and sub.push
    stranger = Principal(
        999,
        False,
        (MembershipView(fwd.id + 100, OrgKind.client, Role.viewer, frozenset()),),
    )
    with pytest.raises(NotFound):
        await n.set_subscription(stranger, ref, push=True, email=True, muted=False)
    with pytest.raises(NotFound):
        await n.set_subscription(viewer, "NOPE", push=True, email=True, muted=False)
