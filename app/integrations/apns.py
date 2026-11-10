"""APNs: HTTP/2-провайдер с токеном ES256 (кэш 50 минут)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
import jwt
import structlog

log = structlog.get_logger()

PushResult = Literal["ok", "gone", "error"]

HOSTS = {"sandbox": "api.sandbox.push.apple.com", "production": "api.push.apple.com"}
TOKEN_TTL = timedelta(minutes=50)
_GONE_REASONS = frozenset({"BadDeviceToken", "Unregistered"})
_BAD_PROVIDER_TOKEN = frozenset({"ExpiredProviderToken", "InvalidProviderToken"})


def _tail(token: str) -> str:
    return token[-6:]


class ApnsSender:
    def __init__(  # noqa: PLR0913 — параметры подключения
        self,
        key_id: str,
        team_id: str,
        key_p8: str,
        bundle_id: str,
        client: httpx.AsyncClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._key_id = key_id
        self._team_id = team_id
        self._key = key_p8
        self._topic = bundle_id
        self._client = client
        self._clock = clock
        self._jwt: str | None = None
        self._jwt_at: datetime | None = None

    def _bearer(self) -> str:
        now = self._clock()
        if self._jwt is None or self._jwt_at is None or now - self._jwt_at >= TOKEN_TTL:
            self._jwt = jwt.encode(
                {"iss": self._team_id, "iat": int(now.timestamp())},
                self._key,
                algorithm="ES256",
                headers={"kid": self._key_id},
            )
            self._jwt_at = now
        return self._jwt

    async def send(
        self, token: str, env: str, title: str, body: str, data: dict[str, str]
    ) -> PushResult:
        host = HOSTS.get(env, HOSTS["sandbox"])
        payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, **data}
        try:
            response = await self._client.post(
                f"https://{host}/3/device/{token}",
                json=payload,
                headers={
                    "authorization": f"bearer {self._bearer()}",
                    "apns-topic": self._topic,
                    "apns-push-type": "alert",
                },
            )
        except httpx.HTTPError as exc:
            log.warning("apns_transport_error", token_tail=_tail(token), error=type(exc).__name__)
            return "error"
        if response.status_code == 200:
            return "ok"
        reason = _reason(response)
        if response.status_code == 410 or (response.status_code == 400 and reason in _GONE_REASONS):
            return "gone"
        if response.status_code == 403 and reason in _BAD_PROVIDER_TOKEN:
            self._jwt = None  # следующая попытка подпишет свежий токен
        log.warning(
            "apns_rejected", token_tail=_tail(token), status=response.status_code, reason=reason
        )
        return "error"


def _reason(response: httpx.Response) -> str | None:
    try:
        value = response.json().get("reason")
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None
