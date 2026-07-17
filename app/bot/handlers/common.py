"""Базовые команды бота: /start, /help."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot import texts

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)
