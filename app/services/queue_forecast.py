"""Прогноз выхода груза из очереди в порту перед морским плечом.

Формула (docs/IOS.md): место в очереди ÷ отгрузка в сутки + простой по
погоде. P50 — ожидаемый срок, P90 — плохой сценарий: отгрузка вдвое
медленнее и непогода вдвое дольше.
"""

from dataclasses import dataclass

from pydantic import BaseModel

BAD_CASE_FACTOR = 2.0


@dataclass(frozen=True, slots=True)
class QueueInput:
    port_code: str
    position: int  # место в очереди (вагоны/контейнеры впереди)
    per_day: float  # отгрузка в сутки
    weather_hours: float  # часы остановки по прогнозу ветра впереди
    basis_code: str  # weather_ban | ferry_wait — что держит очередь


class QueueForecast(BaseModel):
    port_code: str
    position: int
    per_day: float
    weather_hours: float
    p50_hours: float
    p90_hours: float
    basis_code: str


def forecast_queue(inp: QueueInput) -> QueueForecast:
    base = inp.position / inp.per_day * 24.0
    return QueueForecast(
        port_code=inp.port_code,
        position=inp.position,
        per_day=inp.per_day,
        weather_hours=inp.weather_hours,
        p50_hours=round(base + inp.weather_hours, 1),
        p90_hours=round(BAD_CASE_FACTOR * (base + inp.weather_hours), 1),
        basis_code=inp.basis_code,
    )
