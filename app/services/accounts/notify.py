"""Уведомления о событиях груза: push (APNs) и e-mail, в фоне.

Подписки — только персональные переопределения: получатель — тот, у кого сейчас
есть доступ к грузу, кроме автора и тех, кто заглушил груз. В тексте — номер груза
и событие; содержимое контейнера, санкции и названия компаний не уходят.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CheckpointEventKind as Kind
from app.db.models import Device, ShipmentEventRow, ShipmentRow, Subscription
from app.db.repositories.accounts import AccountsRepository
from app.integrations.apns import PushResult
from app.services.accounts.access import (
    Principal,
    can_view,
    load_principal,
    shipment_access,
)
from app.services.accounts.mail import EmailSender, render
from app.services.accounts.shipments import load_shipment
from app.services.corridor import NODES

log = structlog.get_logger()

RETRY_DELAY = 30.0
ENVIRONMENTS = frozenset({"sandbox", "production"})
TOKEN_MIN, TOKEN_MAX = 64, 200
_HEX = frozenset("0123456789abcdefABCDEF")

_HOLD_RU = {
    "weather_ban": "погодный запрет",
    "customs_wait": "таможня",
    "ferry_loading_wait": "ожидание парома",
}
_HOLD_EN = {
    "weather_ban": "weather ban",
    "customs_wait": "customs",
    "ferry_loading_wait": "waiting for ferry",
}


class PushSender(Protocol):
    async def send(
        self, token: str, env: str, title: str, body: str, data: dict[str, str]
    ) -> PushResult: ...


class LogPushSender:
    """Без ключей APNs: в журнал — только номер груза, токен не пишем."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, str, dict[str, str]]] = []

    async def send(
        self, token: str, env: str, title: str, body: str, data: dict[str, str]
    ) -> PushResult:
        self.sent.append((token, env, title, body, data))
        log.info("push_logged", ref=title)
        return "ok"


def _node_name(code: str, lang: str) -> str:
    node = NODES.get(code)
    if node is None:
        return code
    return (node.name_en or node.name) if lang == "en" else node.name


def event_text(ref: str, kind: Kind | str, node_code: str, hold_code: str | None, lang: str) -> str:
    kind = Kind(kind)
    en = lang == "en"
    node = _node_name(node_code, lang)
    if kind is Kind.arrived:
        return f"{ref}: arrived at {node}" if en else f"{ref}: прибыл в {node}"
    if kind is Kind.departed:
        return f"{ref}: departed {node}" if en else f"{ref}: убыл из {node}"
    if kind is Kind.released:
        return f"{ref}: released at {node}" if en else f"{ref}: снят со стоянки в {node}"
    reason = (_HOLD_EN if en else _HOLD_RU).get(hold_code or "")
    base = f"{ref}: held at {node}" if en else f"{ref}: стоит в {node}"
    return f"{base} — {reason}" if reason else base


def route_changed_text(ref: str, lang: str) -> str:
    return f"{ref}: route changed" if lang == "en" else f"{ref}: изменён маршрут"


def _log_failure(result: object, user_id: int, shipment_id: int) -> None:
    if isinstance(result, BaseException):
        log.error(
            "notify_recipient_failed",
            user_id=user_id,
            shipment_id=shipment_id,
            error=type(result).__name__,
        )


@dataclass(frozen=True)
class _Target:
    device_id: int
    token: str
    env: str


@dataclass(frozen=True)
class _Recipient:
    user_id: int
    email: str | None  # None — канал выключен
    lang: str
    devices: tuple[_Target, ...]  # пусто — push выключен или устройств нет


class ShipmentNotifier:
    def __init__(  # noqa: PLR0913 — зависимости
        self,
        session_factory: async_sessionmaker[AsyncSession],
        push: PushSender,
        mail: EmailSender,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sf = session_factory
        self._push = push
        self._mail = mail
        self._sleep = sleep
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    # --- события ---------------------------------------------------------

    async def on_event(
        self, event: ShipmentEventRow, shipment: ShipmentRow, author_id: int
    ) -> None:
        kind, node, hold = Kind(event.kind), event.node_code, event.hold_code
        self._schedule(
            shipment,
            author_id,
            lambda lang: event_text(shipment.ref, kind, node, hold, lang),
        )

    async def on_route_changed(self, shipment: ShipmentRow, author_id: int) -> None:
        self._schedule(
            shipment,
            author_id,
            lambda lang: route_changed_text(shipment.ref, lang),
        )

    def _schedule(self, shipment: ShipmentRow, author_id: int, text: Callable[[str], str]) -> None:
        coro = self._deliver(shipment.id, shipment.org_id, shipment.ref, author_id, text)
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # --- доставка --------------------------------------------------------

    async def _deliver(
        self, shipment_id: int, org_id: int, ref: str, author_id: int, text: Callable[[str], str]
    ) -> None:
        try:
            recipients = await self._recipients(shipment_id, org_id, author_id)
            results = await asyncio.gather(
                *(self._notify(r, shipment_id, ref, text) for r in recipients),
                return_exceptions=True,
            )
            for r, result in zip(recipients, results, strict=True):
                _log_failure(result, r.user_id, shipment_id)
        except Exception:
            log.exception("notify_failed", shipment_id=shipment_id)

    async def _recipients(self, shipment_id: int, org_id: int, author_id: int) -> list[_Recipient]:
        async with self._sf() as session:
            repo = AccountsRepository(session)
            row = await repo.shipments_by_ids([shipment_id])
            if not row:
                return []
            access = await shipment_access(session, row[0])
            users = await repo.users_in_orgs({org_id, *access.shared_org_ids})
            overrides = await repo.subscriptions_for(shipment_id)
            viewers = []
            for user in users:
                if user.id == author_id:
                    continue
                override = overrides.get(user.id)
                if override is not None and override.muted_at is not None:
                    continue
                if can_view(await load_principal(session, user), access):
                    viewers.append((user, override))
            devices = await repo.active_devices([u.id for u, _ in viewers])
        out = []
        for user, override in viewers:
            push_on = override is None or override.push
            email_on = override is None or override.email
            out.append(
                _Recipient(
                    user_id=user.id,
                    email=user.email if email_on else None,
                    lang=user.locale or "ru",
                    devices=tuple(
                        _Target(d.id, d.apns_token, d.environment)
                        for d in devices
                        if push_on and d.user_id == user.id
                    ),
                )
            )
        return out

    async def _notify(
        self, r: _Recipient, shipment_id: int, ref: str, text: Callable[[str], str]
    ) -> None:
        body = text(r.lang)
        jobs = [self._push_one(r, d, shipment_id, ref, body) for d in r.devices]
        if r.email is not None:
            jobs.append(self._email_one(r, shipment_id, body))
        for result in await asyncio.gather(*jobs, return_exceptions=True):
            _log_failure(result, r.user_id, shipment_id)

    async def _push_one(
        self, r: _Recipient, d: _Target, shipment_id: int, ref: str, body: str
    ) -> None:
        async def attempt() -> PushResult:
            try:
                return await self._push.send(d.token, d.env, ref, body, {"ref": ref})
            except Exception as exc:
                log.warning(
                    "push_failed",
                    user_id=r.user_id,
                    shipment_id=shipment_id,
                    error=type(exc).__name__,
                )
                return "error"

        result = await attempt()
        if result == "error":
            await self._sleep(RETRY_DELAY)
            if await self._still_valid(r.user_id, shipment_id, d.device_id):
                result = await attempt()
        if result == "gone":
            await self._revoke(d.device_id)
        elif result == "error":
            log.warning("push_gave_up", user_id=r.user_id, shipment_id=shipment_id)

    async def _email_one(self, r: _Recipient, shipment_id: int, body: str) -> None:
        subject, text = render("event", r.lang, text=body)
        for attempt in (1, 2):
            try:
                assert r.email is not None
                await self._mail.send(r.email, subject, text)
                return
            except Exception as exc:
                log.warning(
                    "email_failed",
                    user_id=r.user_id,
                    shipment_id=shipment_id,
                    attempt=attempt,
                    error=type(exc).__name__,
                )
                if attempt == 1:
                    await self._sleep(RETRY_DELAY)
                    if not await self._still_valid(r.user_id, shipment_id, None):
                        return

    async def _still_valid(self, user_id: int, shipment_id: int, device_id: int | None) -> bool:
        """Перед повтором: снимок 30-секундной давности мог устареть."""
        try:
            async with self._sf() as session:
                repo = AccountsRepository(session)
                if device_id is not None:
                    device = await session.get(Device, device_id)
                    if device is None or device.user_id != user_id or device.revoked_at is not None:
                        return False
                rows = await repo.shipments_by_ids([shipment_id])
                user = await repo.get_user(user_id)
                if not rows or user is None:
                    return False
                sub = await repo.get_subscription(user_id, shipment_id)
                if sub is not None and sub.muted_at is not None:
                    return False
                access = await shipment_access(session, rows[0])
                return can_view(await load_principal(session, user), access)
        except Exception as exc:
            log.error(
                "notify_recheck_failed",
                user_id=user_id,
                shipment_id=shipment_id,
                error=type(exc).__name__,
            )
            return False

    async def _revoke(self, device_id: int) -> None:
        try:
            async with self._sf() as session:
                device = await session.get(Device, device_id)
                if device is not None and device.revoked_at is None:
                    device.revoked_at = self._clock()
                    await session.commit()
        except Exception as exc:
            log.error("device_revoke_failed", device_id=device_id, error=type(exc).__name__)

    # --- устройства и подписки -------------------------------------------

    async def register_device(self, user_id: int, token: str, env: str) -> None:
        if env not in ENVIRONMENTS:
            raise ValueError("bad_environment")
        if not TOKEN_MIN <= len(token) <= TOKEN_MAX or not set(token) <= _HEX:
            raise ValueError("bad_token")
        async with self._sf() as session:
            repo = AccountsRepository(session)
            device = await repo.device_by_token(token)
            if device is None:
                repo.add(Device(user_id=user_id, apns_token=token, environment=env))
            else:
                device.user_id = user_id
                device.environment = env
                device.revoked_at = None
            await session.commit()

    async def set_subscription(
        self, actor: Principal, ref: str, *, push: bool, email: bool, muted: bool
    ) -> None:
        async with self._sf() as session:
            shipment, _ = await load_shipment(session, actor, ref, manage=False)
            repo = AccountsRepository(session)
            sub = await repo.get_subscription(actor.user_id, shipment.id)
            if sub is None:
                sub = Subscription(user_id=actor.user_id, shipment_id=shipment.id)
                repo.add(sub)
            sub.push, sub.email = push, email
            if not muted:
                sub.muted_at = None
            elif sub.muted_at is None:
                sub.muted_at = self._clock()
            await session.commit()
