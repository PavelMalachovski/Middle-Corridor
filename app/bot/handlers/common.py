"""Базовые команды бота: /start, /help, /status + кнопки главного меню."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.keyboards import main_menu_kb, weather_ports_kb
from app.services.formatting import format_corridor_status, format_port_detail
from app.services.manual_reports import ManualReportsService
from app.services.status_aggregator import StatusAggregatorService

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START, reply_markup=main_menu_kb())


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=main_menu_kb())


async def _send_corridor_status(message: Message, status_service: StatusAggregatorService) -> None:
    status = await status_service.get_corridor_status()
    await message.answer(format_corridor_status(status))


@router.message(Command("status"))
async def cmd_status(
    message: Message, command: CommandObject, status_service: StatusAggregatorService
) -> None:
    if command.args:
        port = await status_service.get_port_status(command.args)
        if port is None:
            await message.answer(texts.STATUS_PORT_NOT_FOUND.format(query=command.args))
            return
        await message.answer(format_port_detail(port))
        return
    await _send_corridor_status(message, status_service)


@router.message(F.text == texts.BTN_STATUS)
async def btn_status(message: Message, status_service: StatusAggregatorService) -> None:
    await _send_corridor_status(message, status_service)


@router.message(F.text == texts.BTN_WEATHER)
async def btn_weather(message: Message, reports_service: ManualReportsService) -> None:
    ports = await reports_service.list_ports()
    await message.answer(texts.WEATHER_CHOOSE_PORT, reply_markup=weather_ports_kb(ports))


@router.callback_query(F.data.startswith("wport:"))
async def weather_port_chosen(
    callback: CallbackQuery, status_service: StatusAggregatorService
) -> None:
    code = callback.data.split(":", 1)[1]
    await callback.answer()
    port = await status_service.get_port_status(code)
    if port is not None:
        await callback.message.answer(format_port_detail(port))
