"""Инициализация бота и диспетчера aiogram."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import router as common_router
from app.bot.handlers.reports import router as reports_router
from app.bot.middlewares import TrustedSourceMiddleware
from app.config import Settings
from app.services.manual_reports import ManualReportsService


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(settings: Settings, reports_service: ManualReportsService) -> Dispatcher:
    """Собирает диспетчер: зависимости в workflow data, whitelist на report-роутере."""
    dp = Dispatcher()
    dp["settings"] = settings
    dp["reports_service"] = reports_service

    trusted = TrustedSourceMiddleware(reports_service)
    reports_router.message.middleware(trusted)
    reports_router.callback_query.middleware(trusted)

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(reports_router)
    return dp
