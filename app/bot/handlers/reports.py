"""FSM-диалог /report: приём оперативных данных от доверенных источников.

Схема диалога:
  /report → тип → порт (кроме простоя на границе) → значения → комментарий.
Роутер закрыт TrustedSourceMiddleware (подключается в bot/main.py).
"""

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.keyboards import ports_kb, report_type_kb
from app.db.models import ReportType
from app.services.manual_reports import ManualReportError, ManualReportsService

router = Router(name="reports")


class ReportForm(StatesGroup):
    choosing_type = State()
    choosing_port = State()
    entering_value = State()
    entering_value2 = State()
    entering_note = State()


_VALUE_PROMPTS = {
    ReportType.queue: texts.REPORT_ASK_VESSELS,
    ReportType.rate: texts.REPORT_ASK_RATE,
    ReportType.border_delay: texts.REPORT_ASK_BORDER,
    ReportType.note: texts.REPORT_ASK_NOTE_TEXT,
}


@router.message(Command("report"))
@router.message(F.text == texts.BTN_REPORT)
async def cmd_report(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReportForm.choosing_type)
    await message.answer(texts.REPORT_CHOOSE_TYPE, reply_markup=report_type_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(texts.REPORT_NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.REPORT_CANCELLED)


@router.callback_query(ReportForm.choosing_type, F.data.startswith("rtype:"))
async def type_chosen(
    callback: CallbackQuery, state: FSMContext, reports_service: ManualReportsService
) -> None:
    report_type = ReportType(callback.data.split(":", 1)[1])
    await state.update_data(report_type=report_type.value)
    await callback.answer()

    if report_type is ReportType.border_delay:
        # простой на границе не привязан к порту
        await state.set_state(ReportForm.entering_value)
        await callback.message.answer(_VALUE_PROMPTS[report_type])
        return

    ports = await reports_service.list_ports()
    await state.set_state(ReportForm.choosing_port)
    await callback.message.answer(texts.REPORT_CHOOSE_PORT, reply_markup=ports_kb(ports))


@router.callback_query(ReportForm.choosing_port, F.data.startswith("rport:"))
async def port_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split(":", 1)[1]
    port_id = None if raw == "skip" else int(raw)
    await state.update_data(port_id=port_id)
    await callback.answer()

    data = await state.get_data()
    report_type = ReportType(data["report_type"])
    await state.set_state(ReportForm.entering_value)
    await callback.message.answer(_VALUE_PROMPTS[report_type])


@router.message(ReportForm.entering_value, F.text)
async def value_entered(
    message: Message, state: FSMContext, reports_service: ManualReportsService
) -> None:
    data = await state.get_data()
    report_type = ReportType(data["report_type"])
    text = message.text.strip()

    if report_type is ReportType.queue:
        try:
            vessels = int(text)
        except ValueError:
            await message.answer(texts.REPORT_BAD_INT)
            return
        await state.update_data(vessels_waiting=vessels)
        await state.set_state(ReportForm.entering_value2)
        await message.answer(texts.REPORT_ASK_FERRY_DATE)
    elif report_type is ReportType.rate:
        try:
            rate = float(text.replace(",", "."))
        except ValueError:
            await message.answer(texts.REPORT_BAD_FLOAT)
            return
        await state.update_data(rate_usd=rate)
        await state.set_state(ReportForm.entering_note)
        await message.answer(texts.REPORT_ASK_COMMENT)
    elif report_type is ReportType.border_delay:
        await state.update_data(border=text)
        await state.set_state(ReportForm.entering_value2)
        await message.answer(texts.REPORT_ASK_DELAY)
    else:  # note
        await state.update_data(note=text)
        await _submit(message, state, reports_service)


@router.message(ReportForm.entering_value2, F.text)
async def value2_entered(
    message: Message, state: FSMContext, reports_service: ManualReportsService
) -> None:
    data = await state.get_data()
    report_type = ReportType(data["report_type"])
    text = message.text.strip()

    if report_type is ReportType.queue:
        if text != "-":
            try:
                date.fromisoformat(text)
            except ValueError:
                await message.answer(texts.REPORT_BAD_DATE)
                return
            await state.update_data(ferry_expected=text)
    else:  # border_delay
        try:
            hours = float(text.replace(",", "."))
        except ValueError:
            await message.answer(texts.REPORT_BAD_FLOAT)
            return
        await state.update_data(delay_hours=hours)

    await state.set_state(ReportForm.entering_note)
    await message.answer(texts.REPORT_ASK_COMMENT)


@router.message(ReportForm.entering_note, F.text)
async def note_entered(
    message: Message, state: FSMContext, reports_service: ManualReportsService
) -> None:
    text = message.text.strip()
    if text != "-":
        await state.update_data(note=text)
    await _submit(message, state, reports_service)


async def _submit(
    message: Message, state: FSMContext, reports_service: ManualReportsService
) -> None:
    data = await state.get_data()
    await state.clear()

    report_type = ReportType(data["report_type"])
    payload: dict = {}
    if report_type is ReportType.queue:
        payload["vessels_waiting"] = data["vessels_waiting"]
        if "ferry_expected" in data:
            payload["ferry_expected"] = data["ferry_expected"]
    elif report_type is ReportType.rate:
        payload["rate_usd"] = data["rate_usd"]
    elif report_type is ReportType.border_delay:
        payload["border"] = data["border"]
        payload["delay_hours"] = data["delay_hours"]

    try:
        result = await reports_service.submit(
            tg_user_id=message.from_user.id,
            report_type=report_type,
            payload=payload,
            note=data.get("note"),
            port_id=data.get("port_id"),
        )
    except ManualReportError as exc:
        await message.answer(texts.REPORT_FAILED.format(error=exc))
        return

    template = (
        texts.REPORT_ACCEPTED_PUBLISHED if result.published else texts.REPORT_ACCEPTED_MODERATION
    )
    await message.answer(template.format(report_id=result.report_id))
