"""Почему груз опаздывает: разбор задержки по причинам.

План может нести интервалы причин (`DelayCause`): шторм в порту, ожидание
парома, таможня. Часы причины — её пересечение с периодом от начала плана до
«сейчас». Сумма частей равна задержке груза: необъяснённый остаток —
«отставание от графика» (`schedule`), перебор — режется пропорционально.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

MIN_DELAY_H = 1.0  # меньше часа — не задержка (как на сайте и в приложении)
MIN_PART_H = 0.1

# hold_code груза → код причины задержки
HOLD_TO_CAUSE = {
    "weather_ban": "weather_ban",
    "ferry_loading_wait": "ferry_wait",
    "ferry_return_wait": "ferry_wait",
    "customs_wait": "customs_wait",
}


@dataclass(frozen=True, slots=True)
class DelayCause:
    code: str  # weather_ban | ferry_wait | customs_wait
    node_code: str | None
    start: datetime
    end: datetime


class DelayPart(BaseModel):
    code: str  # weather_ban | ferry_wait | customs_wait | schedule
    node_code: str | None = None
    hours: float


def _hours(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / 3600.0, 0.0)


def breakdown(
    causes: Sequence[DelayCause],
    since: datetime,
    now: datetime,
    delay_hours: float,
    fallback: DelayPart | None,
) -> list[DelayPart]:
    if delay_hours < MIN_DELAY_H:
        return []
    if not causes:
        return [fallback.model_copy(update={"hours": round(delay_hours, 1)})] if fallback else []
    parts: dict[tuple[str, str | None], float] = {}
    for cause in causes:
        hours = _hours(max(cause.start, since), min(cause.end, now))
        if hours >= MIN_PART_H:
            key = (cause.code, cause.node_code)
            parts[key] = parts.get(key, 0.0) + hours
    explained = sum(parts.values())
    if explained > delay_hours and explained > 0:
        scale = delay_hours / explained
        parts = {key: hours * scale for key, hours in parts.items()}
    elif delay_hours - explained >= MIN_DELAY_H:
        parts[("schedule", None)] = delay_hours - explained
    out = [
        DelayPart(code=code, node_code=node, hours=round(hours, 1))
        for (code, node), hours in parts.items()
        if hours >= MIN_PART_H
    ]
    return sorted(out, key=lambda p: -p.hours)
