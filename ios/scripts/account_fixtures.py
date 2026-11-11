"""Снимает фикстуры API аккаунтов для MCCore: me.json, my_shipments.json, events.json.

Поднимает настоящее FastAPI-приложение в процессе (SQLite в памяти, письма — в лог,
часы зафиксированы), как tests/test_accounts_api.py, и сохраняет ответы как есть.
Адреса — example.com, контейнер демо — CSQU3054383; личных данных нет.
Запуск: .venv/bin/python ios/scripts/account_fixtures.py (идемпотентно; нужен пакет app).
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.main import create_app
from app.config import Settings
from app.db.base import Base
from app.db.models import OrgKind, Role
from app.integrations.mock.fleet import ROUTE_KOSTANAY
from app.main import build_accounts, build_map_service
from app.services.accounts.mail import LogEmailSender
from app.services.accounts.notify import LogPushSender

OUT = Path(__file__).resolve().parent.parent / "MCCore/Tests/MCCoreTests/Fixtures/account"
NOW = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
OWNER = "owner@example.com"
AGENT = "agent@example.com"
CONTAINER = "CSQU3054383"


def _dump(name: str, data: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    mail = LogEmailSender()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        auth_secret="fixtures-secret",
        mock_data=False,
        wind_grid_enabled=False,
        web_dist_dir="",
    )
    acc = build_accounts(
        settings, session_factory, clock=lambda: NOW, mail=mail, push=LogPushSender()
    )
    assert acc is not None
    app = create_app(
        settings=settings,
        map_service=build_map_service(settings, session_factory),
        accounts=acc,
    )
    transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 1234))

    async def login(client: httpx.AsyncClient, email: str) -> dict:
        await client.post("/api/v1/auth/code", json={"email": email})
        await asyncio.sleep(0.2)  # письмо уходит в фоне
        code = re.search(r"\b(\d{6})\b", mail.sent[-1][2]).group(1)  # type: ignore[union-attr]
        r = await client.post(
            "/api/v1/auth/verify", json={"email": email, "code": code, "device_name": "iPhone"}
        )
        r.raise_for_status()
        return r.json()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        org = await acc.orgs.create_org(None, "Demo Forwarder", OrgKind.forwarder)
        await acc.orgs.invite(None, org.id, OWNER, Role.owner, [])
        await acc.orgs.invite(None, org.id, AGENT, Role.agent, ["AKTAU"])
        owner = await login(client, OWNER)
        head = {"Authorization": f"Bearer {owner['token']}"}
        r = await client.post(
            "/api/v1/my/shipments",
            headers=head,
            json={
                "org_id": org.id,
                "container_no": CONTAINER,
                "route": ROUTE_KOSTANAY,
                "planned_departure_at": "2027-03-01T08:00:00+00:00",
                "cargo": "Запчасти",
            },
        )
        r.raise_for_status()
        ref = r.json()["shipment"]["ref"]
        for body in (
            {
                "kind": "departed",
                "node_code": ROUTE_KOSTANAY[0],
                "occurred_at": "2027-03-01T09:00:00Z",
            },
            {"kind": "arrived", "node_code": "AKTAU", "occurred_at": "2027-03-08T10:00:00Z"},
            {
                "kind": "held",
                "node_code": "AKTAU",
                "occurred_at": "2027-03-08T12:00:00Z",
                "hold_code": "weather_ban",
                "note": "Шторм",
            },
        ):
            (
                await client.post(f"/api/v1/my/shipments/{ref}/events", headers=head, json=body)
            ).raise_for_status()

        _dump("me.json", owner["me"])
        mine = (await client.get("/api/v1/my/shipments", headers=head)).json()
        _dump("my_shipments.json", mine)
        events = (await client.get(f"/api/v1/my/shipments/{ref}/events", headers=head)).json()
        _dump("events.json", events)
    await acc.aclose()
    await engine.dispose()
    print(f"ok: {OUT} ({ref}, {len(events)} событий)")


if __name__ == "__main__":
    asyncio.run(main())
