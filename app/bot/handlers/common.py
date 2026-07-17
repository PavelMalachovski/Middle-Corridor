"""Базовые команды бота: /start, /help, /status."""

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.bot import texts
from app.services.formatting import format_corridor_status, format_port_detail
from app.services.status_aggregator import StatusAggregatorService

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


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
    status = await status_service.get_corridor_status()
    await message.answer(format_corridor_status(status))
