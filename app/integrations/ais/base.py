"""Интерфейсы AIS-провайдеров.

Известное ограничение (заложено в архитектуру): покрытие AIS на Каспии
слабое — мало береговых приёмников, суда подолгу «пропадают». Поэтому
отсутствие позиции значит «нет данных», а не «судно стоит».
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AISPosition:
    """Позиция судна из AIS."""

    mmsi: int
    lat: float
    lon: float
    sog: float | None  # скорость, узлы
    cog: float | None  # курс, градусы
    nav_status: str | None
    ts: datetime
    ship_name: str | None = None


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Географический прямоугольник для фильтра стрима."""

    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float

    @classmethod
    def parse(cls, raw: str) -> "BoundingBox":
        """Из строки конфига: "lat_min,lon_min,lat_max,lon_max"."""
        parts = [float(part) for part in raw.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Ожидается 4 числа через запятую, получено: {raw!r}")
        return cls(*parts)

    def to_aisstream(self) -> list[list[float]]:
        return [[self.lat_min, self.lon_min], [self.lat_max, self.lon_max]]


class AISProviderError(RuntimeError):
    """Стрим/провайдер AIS вернул ошибку."""


class AISStreamProvider(Protocol):
    def stream(
        self, boxes: list[BoundingBox], mmsi_filter: list[int] | None = None
    ) -> AsyncIterator[AISPosition]: ...
