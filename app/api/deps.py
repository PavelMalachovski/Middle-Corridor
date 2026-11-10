"""Зависимости API аккаунтов: сервисы, вызывающий по bearer-токену, адрес клиента."""

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import User
from app.services.accounts.access import Principal, load_principal
from app.services.accounts.auth import AuthService
from app.services.accounts.events import EventService
from app.services.accounts.notify import ShipmentNotifier
from app.services.accounts.orgs import OrgService
from app.services.accounts.shipments import ShipmentService
from app.services.accounts.views import ProfileService


@dataclass
class AccountsServices:
    """Сервисы аккаунтов одного процесса (собирает `app.main.build_accounts`)."""

    auth: AuthService
    orgs: OrgService
    shipments: ShipmentService
    events: EventService
    notifier: ShipmentNotifier
    profile: ProfileService
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    clock: Callable[[], datetime]
    clients: list[httpx.AsyncClient] = field(default_factory=list)

    async def aclose(self) -> None:
        """Дождаться фоновых уведомлений и закрыть HTTP-клиенты (APNs, Resend)."""
        await self.notifier.drain()
        for client in self.clients:
            await client.aclose()


@dataclass(frozen=True)
class Caller:
    user: User
    principal: Principal
    token: str


def accounts(request: Request) -> AccountsServices:
    """Аккаунты выключены (MOCK_DATA, нет AUTH_SECRET, Vercel) — 404, как будто роутов нет."""
    services = getattr(request.app.state, "accounts", None)
    if services is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return services


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401, detail="unauthorized", headers={"WWW-Authenticate": "Bearer"}
    )


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return token


async def current_caller(
    services: Annotated[AccountsServices, Depends(accounts)],
    authorization: Annotated[str | None, Header()] = None,
) -> Caller:
    """Пользователь и права — на каждый запрос заново: отзыв членства и блокировка
    действуют сразу, без перевыпуска токена."""
    token = _bearer(authorization)
    user = await services.auth.authenticate(token)
    if user is None:
        raise _unauthorized()
    async with services.session_factory() as session:
        principal = await load_principal(session, user)
    return Caller(user, principal, token)


async def current_principal(caller: Annotated[Caller, Depends(current_caller)]) -> Principal:
    return caller.principal


def client_ip(request: Request) -> str:
    """Адрес клиента для лимитов и аудита.

    За доверенным прокси (TRUST_PROXY) — запись X-Forwarded-For на позиции
    TRUSTED_PROXY_HOPS справа: её дописал наш прокси, левее — что прислал клиент.
    Нет такой записи или это не IP — адрес сокета.
    """
    settings: Settings = request.app.state.settings
    peer = request.client.host if request.client else ""
    if not settings.trust_proxy:
        return peer
    hops = settings.trusted_proxy_hops
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
    if hops < 1 or len(entries) < hops:
        return peer
    try:
        return str(ipaddress.ip_address(entries[-hops]))
    except ValueError:
        return peer
