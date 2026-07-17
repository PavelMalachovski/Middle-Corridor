"""Форматирование сообщений для Telegram (HTML).

Единый стиль канала: эмодзи-маркер уровня, компактный текст под мобильный
экран, метка времени обновления.
"""

from datetime import datetime

from app.db.models import AlertLevel, CorridorLeg, Port
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
