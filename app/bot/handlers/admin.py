"""Админ-команды: модерация сводок и управление whitelist.

Роутер целиком закрыт фильтром по ADMIN_USER_IDS из конфига.
"""

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import REPORT_TYPE_LABELS
from app.config import Settings
from app.db.models import ManualReport
from app.services.manual_reports import ManualReportError, ManualReportsService
from app.services.news_feed import NewsFeedService
from app.services.weather_predictor import WeatherPredictor

router = Router(name="admin")


class AdminFilter(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and message.from_user.id in settings.admin_user_ids


router.message.filter(AdminFilter())


def _parse_id(command: CommandObject) -> int | None:
    if command.args is None:
        return None
    try:
        return int(command.args.strip())
    except ValueError:
        return None


def _pending_line(report: ManualReport) -> str:
    header = REPORT_TYPE_LABELS.get(report.report_type.value, report.report_type.value)
    port = f" · {report.port.name}" if report.port is not None else ""
    payload = ", ".join(f"{k}={v}" for k, v in report.payload.items()) or "—"
    author = report.source.name if report.source is not None else "?"
    return (
        f"#{report.id} {header}{port}\n"
        f"    {html.escape(payload)} · от {html.escape(author)} · {report.ts:%d.%m %H:%M}"
    )


@router.message(Command("pending"))
async def cmd_pending(message: Message, reports_service: ManualReportsService) -> None:
    reports = await reports_service.list_pending()
    if not reports:
        await message.answer(texts.PENDING_EMPTY)
        return
    lines = [texts.PENDING_HEADER] + [_pending_line(report) for report in reports]
    lines.append("\n/approve &lt;id&gt; — опубликовать, /reject &lt;id&gt; — отклонить")
    await message.answer("\n".join(lines))


@router.message(Command("approve"))
async def cmd_approve(
    message: Message, command: CommandObject, reports_service: ManualReportsService
) -> None:
    report_id = _parse_id(command)
    if report_id is None:
        await message.answer(texts.APPROVE_USAGE)
        return
    try:
        await reports_service.approve(report_id)
    except ManualReportError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await message.answer(texts.APPROVED.format(report_id=report_id))


@router.message(Command("reject"))
async def cmd_reject(
    message: Message, command: CommandObject, reports_service: ManualReportsService
) -> None:
    report_id = _parse_id(command)
    if report_id is None:
        await message.answer(texts.REJECT_USAGE)
        return
    try:
        await reports_service.reject(report_id)
    except ManualReportError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await message.answer(texts.REJECTED.format(report_id=report_id))


@router.message(Command("poll_weather"))
async def cmd_poll_weather(message: Message, weather_predictor: WeatherPredictor) -> None:
    progress = await message.answer(texts.POLL_WEATHER_RUNNING)
    stats = await weather_predictor.poll_once()
    text = texts.POLL_WEATHER_DONE.format(ports=stats.ports_polled, errors=stats.errors)
    if stats.transitions:
        text += "\nПереходы: " + "; ".join(stats.transitions)
    await progress.edit_text(text)


@router.message(Command("poll_news"))
async def cmd_poll_news(message: Message, news_service: NewsFeedService) -> None:
    progress = await message.answer(texts.POLL_NEWS_RUNNING)
    stats = await news_service.run_once()
    await progress.edit_text(
        texts.POLL_NEWS_DONE.format(stored=stats.stored, published=stats.published)
    )


@router.message(Command("add_source"))
async def cmd_add_source(
    message: Message, command: CommandObject, reports_service: ManualReportsService
) -> None:
    parts = command.args.split(maxsplit=2) if command.args else []
    if len(parts) < 3:
        await message.answer(texts.ADD_SOURCE_USAGE)
        return
    raw_id, role, name = parts
    try:
        tg_user_id = int(raw_id)
    except ValueError:
        await message.answer(texts.ADD_SOURCE_USAGE)
        return
    source = await reports_service.add_trusted_source(tg_user_id, name.strip(), role.strip())
    await message.answer(
        texts.SOURCE_ADDED.format(name=html.escape(source.name), role=html.escape(source.role))
    )
