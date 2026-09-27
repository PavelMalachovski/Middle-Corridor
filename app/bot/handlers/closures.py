"""Журнал фактических остановок портов: /closed, /reopened (админы и доверенные
источники), /closure, /accuracy, /calibrate (только админы).

Факты — эталон для калибровки порогов ветра (services/predictor_accuracy.py).
"""

import html
from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot import texts
from app.config import Settings
from app.db.models import ClosureCause
from app.services.formatting import format_accuracy, format_calibration
from app.services.manual_reports import ManualReportsService
from app.services.predictor_accuracy import (
    ClosureError,
    ClosureInfo,
    PredictorAccuracyService,
)

router = Router(name="closures")

CAUSE_WORDS = {
    "ветер": ClosureCause.wind,
    "шторм": ClosureCause.wind,
    "wind": ClosureCause.wind,
    "другое": ClosureCause.other,
    "other": ClosureCause.other,
}
CAUSE_LABELS = {ClosureCause.wind: "ветер", ClosureCause.other: "другое"}
DEFAULT_ACCURACY_DAYS = 90
DEFAULT_CALIBRATION_DAYS = 365
MAX_DAYS = 3650


def parse_cause_note(words: list[str]) -> tuple[ClosureCause, str | None]:
    """[причина] [комментарий…]; без явной причины — ветер, всё остальное — комментарий."""
    if words and words[0].lower() in CAUSE_WORDS:
        return CAUSE_WORDS[words[0].lower()], " ".join(words[1:]) or None
    return ClosureCause.wind, " ".join(words) or None


def parse_utc(raw: str) -> datetime:
    """2024-11-12T06:00 (UTC) → aware datetime; ValueError на мусоре."""
    value = datetime.fromisoformat(raw)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_days(raw: str | None, default: int) -> int | None:
    if not raw:
        return default
    try:
        days = int(raw)
    except ValueError:
        return None
    return days if 1 <= days <= MAX_DAYS else None


def _fmt(ts: datetime) -> str:
    return ts.strftime("%d.%m.%Y %H:%M UTC")


def _hours(info: ClosureInfo) -> str:
    return f"{info.duration.total_seconds() / 3600:.0f}" if info.duration is not None else "?"


async def _can_report(
    message: Message, settings: Settings, reports_service: ManualReportsService
) -> bool:
    user = message.from_user
    if user is None:
        return False
    if user.id in settings.admin_user_ids or await reports_service.is_trusted(user.id):
        return True
    await message.answer(texts.CLOSURE_DENIED)
    return False


def _is_admin(message: Message, settings: Settings) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_user_ids


@router.message(Command("closed"))
async def cmd_closed(
    message: Message,
    command: CommandObject,
    settings: Settings,
    reports_service: ManualReportsService,
    accuracy_service: PredictorAccuracyService,
) -> None:
    if not await _can_report(message, settings, reports_service):
        return
    words = (command.args or "").split()
    if not words:
        await message.answer(texts.CLOSED_USAGE)
        return
    cause, note = parse_cause_note(words[1:])
    try:
        info = await accuracy_service.close_port(
            words[0], cause=cause, note=note, reported_by=message.from_user.id
        )
    except ClosureError as exc:
        await message.answer(texts.CLOSURE_FAILED.format(error=html.escape(str(exc))))
        return
    await message.answer(
        texts.CLOSED_OK.format(
            port=html.escape(info.port_name),
            ts=_fmt(info.started_at),
            cause=CAUSE_LABELS[info.cause],
            code=info.port_code.lower(),
        )
    )


@router.message(Command("reopened"))
async def cmd_reopened(
    message: Message,
    command: CommandObject,
    settings: Settings,
    reports_service: ManualReportsService,
    accuracy_service: PredictorAccuracyService,
) -> None:
    if not await _can_report(message, settings, reports_service):
        return
    if not command.args:
        await message.answer(texts.REOPENED_USAGE)
        return
    try:
        info = await accuracy_service.reopen_port(command.args.split()[0])
    except ClosureError as exc:
        await message.answer(texts.CLOSURE_FAILED.format(error=html.escape(str(exc))))
        return
    await message.answer(
        texts.REOPENED_OK.format(port=html.escape(info.port_name), hours=_hours(info))
    )


@router.message(Command("closure"))
async def cmd_closure(
    message: Message,
    command: CommandObject,
    settings: Settings,
    accuracy_service: PredictorAccuracyService,
) -> None:
    if not _is_admin(message, settings):
        return  # админские команды для остальных молчат, как весь admin-роутер
    words = (command.args or "").split()
    if len(words) < 3:
        await message.answer(texts.CLOSURE_USAGE)
        return
    try:
        started_at, ended_at = parse_utc(words[1]), parse_utc(words[2])
    except ValueError:
        await message.answer(texts.CLOSURE_USAGE)
        return
    cause, note = parse_cause_note(words[3:])
    try:
        info = await accuracy_service.add_closure(
            words[0],
            started_at,
            ended_at,
            cause=cause,
            note=note,
            reported_by=message.from_user.id,
        )
    except ClosureError as exc:
        await message.answer(texts.CLOSURE_FAILED.format(error=html.escape(str(exc))))
        return
    await message.answer(
        texts.CLOSURE_OK.format(
            port=html.escape(info.port_name),
            start=_fmt(info.started_at),
            end=_fmt(info.ended_at) if info.ended_at is not None else "…",
            hours=_hours(info),
            cause=CAUSE_LABELS[info.cause],
        )
    )


@router.message(Command("accuracy"))
async def cmd_accuracy(
    message: Message,
    command: CommandObject,
    settings: Settings,
    accuracy_service: PredictorAccuracyService,
) -> None:
    if not _is_admin(message, settings):
        return
    days = parse_days(command.args, DEFAULT_ACCURACY_DAYS) or DEFAULT_ACCURACY_DAYS
    ports = await accuracy_service.accuracy(days)
    await message.answer(format_accuracy(ports, days))


@router.message(Command("calibrate"))
async def cmd_calibrate(
    message: Message,
    command: CommandObject,
    settings: Settings,
    accuracy_service: PredictorAccuracyService,
) -> None:
    if not _is_admin(message, settings):
        return
    words = (command.args or "").split()
    days = parse_days(words[1] if len(words) > 1 else None, DEFAULT_CALIBRATION_DAYS)
    if not words or days is None:
        await message.answer(texts.CALIBRATE_USAGE)
        return
    try:
        report = await accuracy_service.calibrate(words[0], days)
    except ClosureError as exc:
        await message.answer(texts.CLOSURE_FAILED.format(error=html.escape(str(exc))))
        return
    await message.answer(format_calibration(report, days))
