"""Интерфейс провайдера погоды.

Любой источник погоды реализует WeatherProvider — в тестах подменяется
фейком, при смене API/тарифа меняется только реализация.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class WindObservation:
    """Ветер в точке в конкретный момент (наблюдение или час прогноза)."""

    wind_speed: float  # устойчивый ветер, м/с
    wind_gust: float  # порывы, м/с
    wind_dir: float  # направление, градусы
    ts: datetime  # время наблюдения/прогноза (UTC)
    raw: dict[str, Any] | None = None  # сырой ответ провайдера


@dataclass(frozen=True, slots=True)
class WindReport:
    """Текущий ветер + почасовой прогноз (отсортирован по времени)."""

    current: WindObservation
    forecast: list[WindObservation]


@dataclass(frozen=True, slots=True)
class GridPointForecast:
    """Почасовой прогноз ветра в узле сетки (для поля ветра над морем)."""

    lat: float
    lon: float
    hours: list[WindObservation]  # отсортированы по времени, без null-хвоста


class WeatherProviderError(RuntimeError):
    """Провайдер погоды недоступен или вернул некорректный ответ."""


class WeatherProvider(Protocol):
    async def get_wind(self, lat: float, lon: float) -> WindReport: ...


class WindGridProvider(Protocol):
    async def get_wind_grid(
        self, points: list[tuple[float, float]], forecast_hours: int
    ) -> list[GridPointForecast]:
        """Прогноз в узлах (lat, lon) на forecast_hours вперёд; порядок узлов сохраняется."""
        ...
