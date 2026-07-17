"""Middleware бота: доступ к report-командам только для whitelist (§7.4)."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot import texts
from app.services.manual_reports import ManualReportsService


class TrustedSourceMiddleware(BaseMiddleware):
    """Пропускает событие, только если пользователь — активный trusted source."""

    def __init__(self, reports_service: ManualReportsService) -> None:
        self._service = reports_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and await self._service.is_trusted(user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(texts.REPORT_DENIED)
        elif isinstance(event, CallbackQuery):
            await event.answer(texts.REPORT_DENIED_SHORT, show_alert=True)
        return None
