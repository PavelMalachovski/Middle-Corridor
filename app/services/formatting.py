"""Форматирование сообщений для Telegram (HTML).

Единый стиль канала: эмодзи-маркер типа/уровня, компактный текст под
мобильный экран, метка времени обновления. Все пользовательские и внешние
строки (новости, ручные сводки) экранируются.
"""

import html
from datetime import datetime
from typing import Any

from app.db.models import AlertLevel, CorridorLeg, NewsItem, Port
from app.integrations.weather.base import WindObservation

LEVEL_EMOJI = {
    AlertLevel.watch: "🌊",
    AlertLevel.warning: "⚠️",
    AlertLevel.critical: "🔴",
}

_LEVEL_TITLE = {
    AlertLevel.watch: "усиление ветра",
    AlertLevel.warning: "риск остановки операций",
    AlertLevel.critical: "вероятна остановка операций",
}


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%d.%m %H:%M UTC")


def _impact_phrase(port: Port) -> str:
    if port.leg == CorridorLeg.caspian:
        return "Вероятны задержки паромов Актау/Курык↔Алят"
    return "Возможны задержки судозаходов и грузовых операций"


def format_weather_alert(port: Port, level: AlertLevel, obs: WindObservation) -> str:
    return (
        f"{LEVEL_EMOJI[level]} <b>{port.name} — {_LEVEL_TITLE[level]}</b>\n"
        f"Ветер {obs.wind_speed:.0f} м/с, порывы до {obs.wind_gust:.0f} м/с. "
        f"{_impact_phrase(port)} в ближайшие 12–24 ч.\n"
        f"<i>Обновлено: {_fmt_ts(obs.ts)}</i>"
    )


def format_weather_all_clear(port: Port, obs: WindObservation) -> str:
    return (
        f"✅ <b>{port.name} — отбой штормового предупреждения</b>\n"
        f"Ветер {obs.wind_speed:.0f} м/с, порывы до {obs.wind_gust:.0f} м/с. "
        f"Условия для операций восстанавливаются.\n"
        f"<i>Обновлено: {_fmt_ts(obs.ts)}</i>"
    )


def format_news_item(item: NewsItem) -> str:
    """Новость для канала: заголовок, краткое содержание, ссылка на источник."""
    lines = [f"📰 <b>{html.escape(item.title)}</b>"]
    if item.summary:
        lines.append(html.escape(_truncate(item.summary, 400)))
    lines.append(
        f'<a href="{html.escape(item.url, quote=True)}">Источник · {html.escape(item.source)}</a>'
    )
    return "\n".join(lines)


_REPORT_HEADER = {
    "queue": "⚓️ Очередь",
    "rate": "💰 Ставка",
    "border_delay": "🚧 Простой на границе",
    "note": "📝 Заметка",
}


def format_manual_report(
    report_type: str,
    payload: dict[str, Any],
    note: str | None,
    ts: datetime,
    port_name: str | None = None,
) -> str:
    """Одобренная ручная сводка для канала.

    payload — гибкое поле: известные ключи выводятся по-человечески,
    остальные парой «ключ: значение».
    """
    header = _REPORT_HEADER.get(report_type, "📌 Сводка")
    title = f"{header} — {html.escape(port_name)}" if port_name else header

    lines = [f"<b>{title}</b>"]
    known = {
        "vessels_waiting": "Судов в ожидании",
        "ferry_expected": "Паром ожидается",
        "rate_usd": "Ставка, USD",
        "delay_hours": "Простой, ч",
        "border": "Граница",
    }
    for key, value in payload.items():
        label = known.get(key, key)
        lines.append(f"{html.escape(str(label))}: {html.escape(str(value))}")
    if note:
        lines.append(html.escape(_truncate(note, 500)))
    lines.append(f"<i>Данные от доверенного источника · {_fmt_ts(ts)}</i>")
    return "\n".join(lines)


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
