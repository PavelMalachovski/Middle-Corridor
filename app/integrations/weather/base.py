"""Интерфейс провайдера погоды.

Любой источник погоды реализует WeatherProvider — в тестах подменяется
фейком, при смене API/тарифа меняется только реализация.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class WindObservation:
    """Текущий ветер в точке."""

    wind_speed: float  # устойчивый ветер, м/с
    wind_gust: float  # порывы, м/с
    wind_dir: float  # направление, градусы
    ts: datetime  # время наблюдения (UTC)
    raw: dict[str, Any] | None = None  # сырой ответ провайдера


class WeatherProviderError(RuntimeError):
    """Провайдер погоды недоступен или вернул некорректный ответ."""


class WeatherProvider(Protocol):
    async def get_current_wind(self, lat: float, lon: float) -> WindObservation: ...
