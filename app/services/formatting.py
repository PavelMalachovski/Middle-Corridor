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
from app.services.status_aggregator import CorridorStatus, PortStatus

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


def format_weather_alert(
    port: Port,
    level: AlertLevel,
    obs: WindObservation,
    forecast_peak: WindObservation | None = None,
) -> str:
    """Алерт по текущим условиям или заблаговременный — по пику прогноза."""
    if forecast_peak is not None:
        body = (
            f"Сейчас {obs.wind_speed:.0f} м/с; к {_fmt_ts(forecast_peak.ts)} ожидается "
            f"усиление до {forecast_peak.wind_speed:.0f} м/с "
            f"(порывы до {forecast_peak.wind_gust:.0f} м/с). "
        )
    else:
        body = f"Ветер {obs.wind_speed:.0f} м/с, порывы до {obs.wind_gust:.0f} м/с. "
    return (
        f"{LEVEL_EMOJI[level]} <b>{port.name} — {_LEVEL_TITLE[level]}</b>\n"
        f"{body}{_impact_phrase(port)} в ближайшие 12–24 ч.\n"
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
    """Новость для канала: русский перевод (если есть), иначе оригинал."""
    title = item.title_ru or item.title
    summary = item.summary_ru or item.summary
    lines = [f"📰 <b>{html.escape(title)}</b>"]
    if summary:
        lines.append(html.escape(_truncate(summary, 400)))
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


# --- Сводный статус коридора (/status) ----------------------------------------

_LEG_TITLE = {
    CorridorLeg.caspian: "Каспий",
    CorridorLeg.black_sea: "Чёрное море",
    CorridorLeg.rail_cis: "Ж/д (КЗ)",
    CorridorLeg.rail_caucasus: "Ж/д (Кавказ)",
    CorridorLeg.europe: "Европа",
}


def _port_line(port: "PortStatus") -> str:
    if port.alert_level is not None:
        marker = LEVEL_EMOJI[port.alert_level]
        detail = port.alert_message or _LEVEL_TITLE[port.alert_level]
    elif port.wind_speed is not None:
        marker = "✅"
        detail = f"ветер {port.wind_speed:.0f} м/с, порывы {port.wind_gust:.0f} м/с"
    else:
        marker = "⚪️"
        detail = "нет данных о погоде"
    return f"{marker} {port.name} — {detail}"


def format_corridor_status(status: "CorridorStatus") -> str:
    lines = ["🗺 <b>Средний коридор — сводка</b>"]

    for leg in CorridorLeg:
        leg_ports = [port for port in status.ports if port.leg == leg]
        if not leg_ports:
            continue
        lines.append(f"\n<b>{_LEG_TITLE[leg]}</b>")
        lines.extend(_port_line(port) for port in leg_ports)

    lines.append("\n⛴ <b>Суда</b>")
    with_data = [vessel for vessel in status.vessels if vessel.has_recent_data]
    without_data = [vessel for vessel in status.vessels if not vessel.has_recent_data]
    for vessel in with_data:
        sog = f", {vessel.sog:.1f} уз" if vessel.sog is not None else ""
        seen = f" ({_fmt_ts(vessel.ts)})" if vessel.ts else ""
        lines.append(f"• {html.escape(vessel.name)} — в эфире{sog}{seen}")
    if without_data:
        if with_data:
            lines.append(f"• нет данных: {len(without_data)} судов")
        else:
            lines.append("нет данных по судам — покрытие AIS на Каспии слабое")

    lines.append("\n⚓️ <b>Оперативные данные</b>")
    if status.recent_reports:
        for report in status.recent_reports:
            header = _REPORT_HEADER.get(report.report_type, "📌")
            port_part = f" {html.escape(report.port_name)}" if report.port_name else ""
            payload = ", ".join(f"{k}: {v}" for k, v in report.payload.items())
            body = html.escape(payload or _truncate(report.note or "", 80))
            lines.append(f"{header}{port_part}: {body} ({_fmt_ts(report.ts)})")
    else:
        lines.append("свежих сводок от источников нет")

    lines.append(f"\n<i>Обновлено: {_fmt_ts(status.generated_at)}</i>")
    return "\n".join(lines)


def format_port_detail(port: "PortStatus") -> str:
    lines = [f"<b>{port.name}</b> ({port.country}) · {_LEG_TITLE[port.leg]}"]
    if port.alert_level is not None:
        marker = LEVEL_EMOJI[port.alert_level]
        lines.append(f"{marker} <b>{_LEVEL_TITLE[port.alert_level]}</b>")
    if port.wind_speed is not None:
        lines.append(f"Ветер {port.wind_speed:.0f} м/с, порывы до {port.wind_gust:.0f} м/с")
        if port.weather_ts is not None:
            lines.append(f"<i>Погода обновлена: {_fmt_ts(port.weather_ts)}</i>")
    else:
        lines.append("Данных о погоде пока нет")
    return "\n".join(lines)
