"""HTTP-слой аккаунтов: вход, компании, мои грузы, события (SQLite, без сети)."""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from starlette.requests import Request

from app.api.deps import AccountsServices, client_ip
from app.api.main import create_app
from app.config import Settings
from app.db.models import OrgKind, Role
from app.integrations.mock.fleet import ROUTE_KOSTANAY
from app.main import build_accounts, build_map_service
from app.services.accounts.mail import LogEmailSender
from app.services.accounts.notify import LogPushSender

NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
DEPART = "2027-03-01T08:00:00+00:00"
CONTAINER = "CSQU3054383"


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "auth_secret": "s3cret",
        "mock_data": False,
        "wind_grid_enabled": False,
        "web_dist_dir": "",
    }
    base.update(kwargs)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


class FailingMail(LogEmailSender):
    async def send(self, to: str, subject: str, text: str) -> None:
        if "Приглашение" in subject or "Invitation" in subject:
            raise RuntimeError("smtp down")
        await super().send(to, subject, text)


class Env:
    def __init__(self, client: httpx.AsyncClient, acc: AccountsServices, mail, push) -> None:
        self.client = client
        self.acc = acc
        self.mail = mail
        self.push = push

    async def login(self, email: str) -> str:
        r = await self.client.post("/api/v1/auth/code", json={"email": email})
        assert r.status_code == 202
        to, _, body = self.mail.sent[-1]
        assert to == email
        code = re.search(r"\b(\d{6})\b", body).group(1)
        r = await self.client.post(
            "/api/v1/auth/verify", json={"email": email, "code": code, "device_name": "iPhone"}
        )
        assert r.status_code == 200, r.text
        return r.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _env(session_factory, mail=None, **settings_kw) -> AsyncIterator[Env]:
    mail = mail or LogEmailSender()
    push = LogPushSender()
    settings = _settings(**settings_kw)
    acc = build_accounts(settings, session_factory, clock=lambda: NOW, mail=mail, push=push)
    assert acc is not None
    app = create_app(
        settings=settings,
        map_service=build_map_service(settings, session_factory),
        accounts=acc,
    )
    transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 1234), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Env(client, acc, mail, push)
    await acc.aclose()


@pytest.fixture
async def env(session_factory) -> AsyncIterator[Env]:
    async for e in _env(session_factory):
        yield e


async def _forwarder(env: Env, owner: str = "owner@x.test") -> int:
    org = await env.acc.orgs.create_org(None, "Fwd", OrgKind.forwarder)
    await env.acc.orgs.invite(None, org.id, owner, Role.owner, [])
    return org.id


async def _create(env: Env, token: str, org_id: int) -> str:
    r = await env.client.post(
        "/api/v1/my/shipments",
        headers=bearer(token),
        json={
            "org_id": org_id,
            "container_no": CONTAINER,
            "route": ROUTE_KOSTANAY,
            "planned_departure_at": DEPART,
            "cargo": "Запчасти",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["shipment"]["ref"]


async def test_accounts_404_in_mock_mode(session_factory) -> None:
    mock = _settings(mock_data=True)
    assert build_accounts(mock, session_factory) is None
    assert build_accounts(_settings(vercel="1"), session_factory) is None
    assert build_accounts(_settings(auth_secret=""), session_factory) is None
    app = create_app(settings=mock, map_service=build_map_service(mock, None))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/auth/code", json={"email": "a@x.test"})).status_code == (
            404
        )
        assert (await client.get("/api/v1/me", headers=bearer("x"))).status_code == 404
        assert (await client.get("/api/v1/my/shipments")).status_code == 404
        assert (await client.get("/api/v1/snapshot")).status_code == 200


async def test_full_flow_invite_login_create_event_notify(env: Env) -> None:
    fwd = await _forwarder(env)
    owner = await env.login("owner@x.test")
    me = (await env.client.get("/api/v1/me", headers=bearer(owner))).json()
    assert me["email"] == "owner@x.test"
    assert me["memberships"] == [
        {
            "org_id": fwd,
            "org_name": "Fwd",
            "org_kind": "forwarder",
            "role": "owner",
            "node_codes": [],
        }
    ]

    ref = await _create(env, owner, fwd)
    mine = (await env.client.get("/api/v1/my/shipments", headers=bearer(owner))).json()
    assert [m["shipment"]["ref"] for m in mine] == [ref]
    assert mine[0]["can_manage"] is True
    assert mine[0]["container_no"] == CONTAINER
    assert mine[0]["org_id"] == fwd
    assert mine[0]["shipment"]["client"] == "Fwd"
    assert "cargo_details" in mine[0]["shipment"]

    r = await env.client.post(
        "/api/v1/me/devices",
        headers=bearer(owner),
        json={"apns_token": "ab" * 32, "environment": "sandbox"},
    )
    assert r.status_code == 204

    r = await env.client.post(
        f"/api/v1/orgs/{fwd}/invitations",
        headers=bearer(owner),
        json={"email": "agent@x.test", "role": "agent", "node_codes": ["AKTAU"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["mail"] == "sent"
    agent = await env.login("agent@x.test")

    detail = (await env.client.get(f"/api/v1/my/shipments/{ref}", headers=bearer(agent))).json()
    assert detail["can_manage"] is False
    assert detail["event_nodes"] == ["AKTAU"]

    r = await env.client.post(
        f"/api/v1/my/shipments/{ref}/events",
        headers=bearer(agent),
        json={"kind": "arrived", "node_code": "AKTAU"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "arrived"
    await env.acc.notifier.drain()

    assert [p[0] for p in env.push.sent] == ["ab" * 32]
    assert ref in env.push.sent[0][2] + env.push.sent[0][3]
    owner_mail = [m for m in env.mail.sent if m[0] == "owner@x.test" and ref in m[1]]
    assert owner_mail

    events = (
        await env.client.get(f"/api/v1/my/shipments/{ref}/events", headers=bearer(owner))
    ).json()
    assert [(e["kind"], e["node_code"], e["superseded"]) for e in events] == [
        ("arrived", "AKTAU", False)
    ]
    detail = (await env.client.get(f"/api/v1/my/shipments/{ref}", headers=bearer(owner))).json()
    assert detail["shipment"]["last_event_node"] == "AKTAU"

    r = await env.client.put(
        f"/api/v1/my/shipments/{ref}/subscription",
        headers=bearer(owner),
        json={"push": False, "email": True, "muted": False},
    )
    assert r.status_code == 204

    r = await env.client.post("/api/v1/auth/logout", headers=bearer(agent))
    assert r.status_code == 204
    assert (await env.client.get("/api/v1/me", headers=bearer(agent))).status_code == 401


async def test_no_token_401_foreign_ref_404(env: Env) -> None:
    r = await env.client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json() == {"detail": "unauthorized"}
    assert r.headers["www-authenticate"] == "Bearer"
    r = await env.client.get("/api/v1/my/shipments", headers=bearer("garbage"))
    assert r.status_code == 401
    r = await env.client.get("/api/v1/me", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401

    fwd = await _forwarder(env)
    owner = await env.login("owner@x.test")
    ref = await _create(env, owner, fwd)
    other = await _forwarder(env, owner="stranger@x.test")
    stranger = await env.login("stranger@x.test")
    for path in (f"/api/v1/my/shipments/{ref}", "/api/v1/my/shipments/MC-27-9999"):
        r = await env.client.get(path, headers=bearer(stranger))
        assert r.status_code == 404
        assert r.json() == {"detail": "not_found"}
    r = await env.client.post(
        f"/api/v1/my/shipments/{ref}/events",
        headers=bearer(stranger),
        json={"kind": "arrived", "node_code": "AKTAU"},
    )
    assert r.status_code == 404
    assert (
        await env.client.get(f"/api/v1/orgs/{fwd}/members", headers=bearer(stranger))
    ).status_code == 404
    assert (
        await env.client.get(f"/api/v1/orgs/{other}/members", headers=bearer(stranger))
    ).status_code == 200


async def test_errors_and_admin_routes(env: Env) -> None:
    fwd = await _forwarder(env)
    owner = await env.login("owner@x.test")
    r = await env.client.post(
        "/api/v1/my/shipments",
        headers=bearer(owner),
        json={
            "org_id": fwd,
            "container_no": "CSQU3054384",
            "route": ROUTE_KOSTANAY,
            "planned_departure_at": DEPART,
        },
    )
    assert r.status_code == 422
    assert r.json() == {"detail": "bad_container"}
    ref = await _create(env, owner, fwd)
    r = await env.client.post(
        f"/api/v1/my/shipments/{ref}/events",
        headers=bearer(owner),
        json={"kind": "teleported", "node_code": "AKTAU"},
    )
    assert r.status_code == 422
    r = await env.client.patch(
        f"/api/v1/my/shipments/{ref}", headers=bearer(owner), json={"cargo": "Шины"}
    )
    assert r.status_code == 200
    assert r.json()["shipment"]["cargo"] == "Шины"
    calls = []

    async def spy(row, author_id):
        calls.append((row.ref, author_id))

    env.acc.notifier.on_route_changed = spy  # type: ignore[method-assign]
    r = await env.client.patch(
        f"/api/v1/my/shipments/{ref}",
        headers=bearer(owner),
        json={"route": ROUTE_KOSTANAY[:-1], "cargo": None, "container_no": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["shipment"]["destination_code"] == "BEINEU"
    assert r.json()["shipment"]["cargo"] == ""
    assert r.json()["container_no"] == CONTAINER
    assert [c[0] for c in calls] == [ref]

    # админка — только платформа
    assert (
        await env.client.post(
            "/api/v1/admin/orgs", headers=bearer(owner), json={"name": "X", "kind": "client"}
        )
    ).status_code == 404
    await env.acc.orgs.set_platform_admin("root@x.test")
    root = await env.login("root@x.test")
    r = await env.client.post(
        "/api/v1/admin/orgs", headers=bearer(root), json={"name": "Client", "kind": "client"}
    )
    assert r.status_code == 201
    client_id = r.json()["id"]
    r = await env.client.post(
        f"/api/v1/admin/orgs/{fwd}/links", headers=bearer(root), json={"client_id": client_id}
    )
    assert r.status_code == 204
    clients = (await env.client.get(f"/api/v1/orgs/{fwd}/clients", headers=bearer(owner))).json()
    assert clients == [{"id": client_id, "name": "Client", "kind": "client"}]
    r = await env.client.post(
        f"/api/v1/admin/orgs/{client_id}/invitations",
        headers=bearer(root),
        json={"email": "buyer@x.test", "role": "owner"},
    )
    assert r.status_code == 201
    r = await env.client.post(
        f"/api/v1/my/shipments/{ref}/share", headers=bearer(owner), json={"org_id": client_id}
    )
    assert r.status_code == 204
    buyer = await env.login("buyer@x.test")
    seen = (await env.client.get("/api/v1/my/shipments", headers=bearer(buyer))).json()
    assert [(s["shipment"]["ref"], s["can_manage"], s["event_nodes"]) for s in seen] == [
        (ref, False, [])
    ]
    r = await env.client.post(f"/api/v1/my/shipments/{ref}/archive", headers=bearer(owner))
    assert r.status_code == 204
    assert (await env.client.get("/api/v1/my/shipments", headers=bearer(buyer))).json() == []

    r = await env.client.patch(
        "/api/v1/me", headers=bearer(owner), json={"name": " Павел ", "locale": "en"}
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["locale"]) == ("Павел", "en")
    r = await env.client.patch("/api/v1/me", headers=bearer(owner), json={"locale": "de"})
    assert r.status_code == 422


async def test_invitation_mail_failure_reported(session_factory) -> None:
    async for env in _env(session_factory, mail=FailingMail()):
        org = await env.acc.orgs.create_org(None, "Fwd", OrgKind.forwarder)
        await env.acc.orgs.set_platform_admin("root@x.test")
        root = await env.login("root@x.test")
        r = await env.client.post(
            f"/api/v1/orgs/{org.id}/invitations",
            headers=bearer(root),
            json={"email": "agent@x.test", "role": "viewer"},
        )
        assert r.status_code == 201
        assert r.json()["mail"] == "failed"
        assert isinstance(r.json()["invitation_id"], int)


async def test_code_endpoint_same_response_for_unknown(env: Env) -> None:
    await _forwarder(env)
    env.mail.sent.clear()  # письмо-приглашение владельцу
    responses = []
    for email in ("owner@x.test", "nobody@x.test", "not-an-email", "a@" + "x" * 300):
        r = await env.client.post("/api/v1/auth/code", json={"email": email})
        responses.append((r.status_code, r.json()))
    assert set(map(str, responses)) == {str((202, {"status": "sent"}))}
    sent = [(m[0], m[1]) for m in env.mail.sent]
    assert sent == [("owner@x.test", "Код входа в Middle Corridor")]
    r = await env.client.post(
        "/api/v1/auth/verify", json={"email": "nobody@x.test", "code": "000000", "device_name": ""}
    )
    assert r.status_code == 401


async def test_body_size_limit_413(env: Env) -> None:
    big = '{"email": "' + "a" * 70_000 + '@x.test"}'
    r = await env.client.post(
        "/api/v1/auth/code", content=big, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413

    async def chunks():
        for _ in range(10):
            yield b"x" * 10_000

    r = await env.client.post(
        "/api/v1/me/devices", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413
    # обычные маленькие запросы проходят
    r = await env.client.post("/api/v1/auth/code", json={"email": "a@x.test"})
    assert r.status_code == 202


async def test_public_snapshot_has_no_real_shipments(env: Env) -> None:
    fwd = await _forwarder(env)
    owner = await env.login("owner@x.test")
    ref = await _create(env, owner, fwd)
    snap = await env.client.get("/api/v1/snapshot")
    assert snap.status_code == 200
    assert ref not in snap.text
    assert snap.json()["shipments"] == []
    assert (await env.client.get(f"/api/v1/shipments/{ref}")).status_code == 404
    assert (
        await env.client.get(f"/api/v1/shipments/{ref}", headers=bearer(owner))
    ).status_code == 404


async def test_revoked_membership_and_disabled_user(env: Env) -> None:
    fwd = await _forwarder(env)
    owner = await env.login("owner@x.test")
    ref = await _create(env, owner, fwd)
    r = await env.client.post(
        f"/api/v1/orgs/{fwd}/invitations",
        headers=bearer(owner),
        json={"email": "ops@x.test", "role": "admin"},
    )
    assert r.status_code == 201
    ops = await env.login("ops@x.test")
    assert (
        await env.client.get(f"/api/v1/my/shipments/{ref}", headers=bearer(ops))
    ).status_code == 200
    members = (await env.client.get(f"/api/v1/orgs/{fwd}/members", headers=bearer(owner))).json()
    by_email = {m["email"]: m for m in members}
    assert by_email["ops@x.test"]["role"] == "admin"

    r = await env.client.delete(
        f"/api/v1/orgs/{fwd}/members/{by_email['ops@x.test']['user_id']}", headers=bearer(owner)
    )
    assert r.status_code == 204
    # тот же токен, но членства уже нет — груз не виден сразу
    assert (
        await env.client.get(f"/api/v1/my/shipments/{ref}", headers=bearer(ops))
    ).status_code == 404
    assert (await env.client.get("/api/v1/my/shipments", headers=bearer(ops))).json() == []
    assert (await env.client.get("/api/v1/me", headers=bearer(ops))).json()["memberships"] == []

    await env.acc.orgs.disable_user("owner@x.test")
    assert (await env.client.get("/api/v1/me", headers=bearer(owner))).status_code == 401


async def test_cors_allows_authorization_header(session_factory) -> None:
    async for env in _env(session_factory, cors_origins="https://app.example"):
        r = await env.client.options(
            "/api/v1/me",
            headers={
                "Origin": "https://app.example",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )
        assert r.status_code == 200
        methods = r.headers["access-control-allow-methods"]
        for method in ("GET", "POST", "PATCH", "PUT", "DELETE"):
            assert method in methods
        assert "authorization" in r.headers["access-control-allow-headers"].lower()


def _request(headers: dict[str, str], trust: bool, hops: int = 1) -> Request:
    settings = _settings(trust_proxy=trust, trusted_proxy_hops=hops)
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("10.0.0.1", 5000),
        "app": type("A", (), {"state": type("S", (), {"settings": settings})}),
    }
    return Request(scope)


def test_client_ip_trusts_proxy_only_when_configured() -> None:
    # клиент подставил 6.6.6.6, прокси дописал настоящий адрес справа
    xff = {"X-Forwarded-For": "6.6.6.6, 1.2.3.4"}
    assert client_ip(_request(xff, trust=False)) == "10.0.0.1"
    assert client_ip(_request(xff, trust=True)) == "1.2.3.4"
    assert client_ip(_request({"X-Forwarded-For": "6.6.6.6, 1.2.3.4, 10.0.0.9"}, True, 2)) == (
        "1.2.3.4"
    )
    assert client_ip(_request({}, trust=True)) == "10.0.0.1"
    assert client_ip(_request({"X-Forwarded-For": "1.2.3.4"}, True, 2)) == "10.0.0.1"
    assert client_ip(_request({"X-Forwarded-For": "6.6.6.6, garbage"}, True)) == "10.0.0.1"
    assert client_ip(_request({"X-Forwarded-For": " , "}, True)) == "10.0.0.1"
    assert client_ip(_request({"X-Forwarded-For": "6.6.6.6, 2001:db8::1"}, True)) == "2001:db8::1"


async def test_value_error_422_only_for_codes(session_factory) -> None:
    async for env in _env(session_factory):
        fwd = await _forwarder(env)
        owner = await env.login("owner@x.test")
        ref = await _create(env, owner, fwd)

        async def coded(*args, **kwargs):
            raise ValueError("bad_route")

        async def raw(*args, **kwargs):
            raise ValueError("invalid literal for int() with base 10: 'secret@x.test'")

        env.acc.shipments.update = coded  # type: ignore[method-assign]
        r = await env.client.patch(
            f"/api/v1/my/shipments/{ref}", headers=bearer(owner), json={"cargo": "x"}
        )
        assert (r.status_code, r.json()) == (422, {"detail": "bad_route"})

        env.acc.shipments.update = raw  # type: ignore[method-assign]
        r = await env.client.patch(
            f"/api/v1/my/shipments/{ref}", headers=bearer(owner), json={"cargo": "x"}
        )
        assert r.status_code == 500
        assert "secret" not in r.text
