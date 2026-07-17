"""Админ-команды: модерация сводок и управление whitelist.

Роутер целиком закрыт фильтром по ADMIN_USER_IDS из конфига.
"""

import html

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.keyboards import REPORT_TYPE_LABELS, moderation_kb
from app.config import Settings
from app.db.models import ManualReport
from app.services.manual_reports import ManualReportError, ManualReportsService
from app.services.news_feed import NewsFeedService
from app.services.weather_predictor import WeatherPredictor

router = Router(name="admin")


class AdminFilter(Filter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id in settings.admin_user_ids


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


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
    await message.answer(texts.PENDING_HEADER.strip())
    shown = reports[:10]
    for report in shown:
        # карточка с кнопками — модерация в один тап
        await message.answer(_pending_line(report), reply_markup=moderation_kb(report.id))
    if len(reports) > len(shown):
        await message.answer(
            f"…и ещё {len(reports) - len(shown)} — повторите /pending после разбора"
        )


@router.callback_query(F.data.startswith("mod:"))
async def moderation_callback(
    callback: CallbackQuery, reports_service: ManualReportsService
) -> None:
    _, action, raw_id = callback.data.split(":", 2)
    report_id = int(raw_id)
    try:
        if action == "approve":
            await reports_service.approve(report_id)
            result = texts.APPROVED.format(report_id=report_id)
        else:
            await reports_service.reject(report_id)
            result = texts.REJECTED.format(report_id=report_id)
    except ManualReportError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Готово")
    # убираем кнопки и фиксируем итог прямо в карточке
    await callback.message.edit_text(f"{callback.message.html_text}\n\n{result}")


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
