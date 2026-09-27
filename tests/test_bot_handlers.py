"""Хендлеры бота: пользовательский ввод в HTML-ответах экранируется."""

from types import SimpleNamespace
from typing import Any

from aiogram.filters import CommandObject

from app.bot.handlers.common import cmd_status
from app.bot.handlers.reports import _submit
from app.services.manual_reports import InvalidPayloadError


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=42)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


class NoPortStatus:
    async def get_port_status(self, query: str) -> None:
        return None


class FakeState:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    async def get_data(self) -> dict[str, Any]:
        return dict(self._data)

    async def clear(self) -> None:
        self._data = {}


class FailingReports:
    async def submit(self, **kwargs: Any) -> None:
        raise InvalidPayloadError("rate_usd: <неверно> & всё")


async def test_status_unknown_port_escapes_query() -> None:
    message = FakeMessage()
    command = CommandObject(command="status", args="<b>aktau")
    await cmd_status(message, command, NoPortStatus())  # type: ignore[arg-type]
    assert "&lt;b&gt;aktau" in message.answers[0]
    assert "<b>" not in message.answers[0]


async def test_report_failure_escapes_error() -> None:
    message = FakeMessage()
    state = FakeState({"report_type": "note", "note": "x"})
    await _submit(message, state, FailingReports())  # type: ignore[arg-type]
    assert "&lt;неверно&gt; &amp; всё" in message.answers[0]
