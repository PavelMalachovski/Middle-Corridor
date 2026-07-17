"""Клавиатуры бота: главное меню (Reply) и inline-выборы."""

from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot import texts
from app.db.models import Port


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Постоянное меню — операторы не любят слэш-команды."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_STATUS), KeyboardButton(text=texts.BTN_WEATHER)],
            [KeyboardButton(text=texts.BTN_REPORT), KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def weather_ports_kb(ports: Sequence[Port]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{port.name} ({port.country})", callback_data=f"wport:{port.code}"
            )
        ]
        for port in ports
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moderation_kb(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать", callback_data=f"mod:approve:{report_id}"
                ),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:reject:{report_id}"),
            ]
        ]
    )


REPORT_TYPE_LABELS = {
    "queue": "⚓️ Очередь в порту",
    "rate": "💰 Ставка",
    "border_delay": "🚧 Простой на границе",
    "note": "📝 Заметка",
}


def report_type_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"rtype:{value}")]
        for value, label in REPORT_TYPE_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ports_kb(ports: Sequence[Port], allow_skip: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{port.name} ({port.country})", callback_data=f"rport:{port.id}"
            )
        ]
        for port in ports
    ]
    if allow_skip:
        rows.append(
            [InlineKeyboardButton(text="— без привязки к порту —", callback_data="rport:skip")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
