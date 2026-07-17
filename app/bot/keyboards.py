"""Inline-клавиатуры бота."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Port

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
