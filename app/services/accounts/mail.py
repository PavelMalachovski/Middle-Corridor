"""Отправка писем: Protocol, журнал для разработки и Resend."""

from typing import Protocol

import httpx
import structlog

from app.services.accounts.security import email_fingerprint

log = structlog.get_logger()

RESEND_URL = "https://api.resend.com/emails"

# Тексты писем: {шаблон: {язык: (тема, тело)}}. Тело — format-строка.
TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "login_code": {
        "ru": ("Код входа в Middle Corridor", "Ваш код входа: {code}\nОн действует 10 минут."),
        "en": (
            "Middle Corridor sign-in code",
            "Your sign-in code: {code}\nIt is valid for 10 minutes.",
        ),
    },
    "invited": {
        "ru": (
            "Приглашение в Middle Corridor",
            "{inviter} приглашает вас в «{org}». Откройте приложение и войдите по этому адресу.",
        ),
        "en": (
            "Invitation to Middle Corridor",
            "{inviter} invited you to “{org}”. Open the app and sign in with this address.",
        ),
    },
    "event": {
        "ru": ("{text}", "{text}\n\nПодробности — в приложении Middle Corridor."),
        "en": ("{text}", "{text}\n\nDetails are in the Middle Corridor app."),
    },
}


def render(template: str, locale: str | None, **params: str) -> tuple[str, str]:
    """Тема и тело письма; неизвестный язык — русский."""
    variants = TEMPLATES[template]
    subject, body = variants.get(locale or "ru", variants["ru"])
    return subject.format(**params), body.format(**params)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None: ...


class LogEmailSender:
    """Для разработки и тестов: в журнал — только отпечаток адреса и тема."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))
        log.info("mail_sent", to_hash=email_fingerprint(to), subject=subject)


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._sender = sender
        self._client = client

    async def send(self, to: str, subject: str, text: str) -> None:
        response = await self._client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"from": self._sender, "to": [to], "subject": subject, "text": text},
        )
        response.raise_for_status()
