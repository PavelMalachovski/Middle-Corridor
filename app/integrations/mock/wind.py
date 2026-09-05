"""Синтетическое поле ветра для прототипа.

Аналитическая модель: фоновый западный перенос + три медленно дрейфующих
вихря (циклон над северным Каспием — источник штормов в Актау/Курыке,
циклон над Чёрным морем, антициклон над степью) + мелкая текстура.
Всё детерминировано по времени: одна и та же минута даёт одно и то же
поле, а в течение суток картина заметно меняется — алерты по портам
эволюционируют, как в жизни.
"""

import math
from collections.abc import Callable
from datetime import UTC, datetime

from app.services.corridor import SEA_BBOX, sea_grid
from app.services.wind_field import WindField, WindPoint

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
GUST_FACTOR = 1.3
GUST_OFFSET = 1.5

# Поле считается только над морем (SEA_BBOX + маска sea_grid): над степью и
# горами ветер ничего не останавливает, а частицы там — шум и нагрузка на GPU.
DEFAULT_BBOX = SEA_BBOX
DEFAULT_STEP = 1.0
MAX_POINTS = 8000  # 0.25° над морями ≈ 1 700 точек


def _hours(t: datetime) -> float:
    return (t - _EPOCH).total_seconds() / 3600.0


def _vortex(
    lat: float,
    lon: float,
    center: tuple[float, float],
    radius_deg: float,
    amplitude: float,
    clockwise: bool,
) -> tuple[float, float]:
    """Тангенциальный ветер вихря (u восток, v север), м/с."""
    dy = lat - center[0]
    dx = (lon - center[1]) * math.cos(math.radians(lat))
    r = math.hypot(dx, dy)
    if r < 1e-6:
        return 0.0, 0.0
    s = r / radius_deg
    speed = amplitude * s * math.exp((1.0 - s * s) / 2.0)  # пик на r = R, быстрый спад
    u, v = -speed * dy / r, speed * dx / r  # против часовой (циклон)
    return (-u, -v) if clockwise else (u, v)


def wind_vector(lat: float, lon: float, t: datetime) -> tuple[float, float]:
    """Компоненты ветра (u восток, v север) в точке в момент t, м/с."""
    h = _hours(t)
    phase = 2 * math.pi * h / 36.0
    u, v = 3.5, 0.5  # фоновый западный перенос

    # Циклон над северным Каспием — ядро штормов Актау/Курыка
    du, dv = _vortex(
        lat,
        lon,
        (44.6 + 0.5 * math.sin(phase), 50.4 + 0.8 * math.cos(phase)),
        1.6,
        17.0,
        clockwise=False,
    )
    u, v = u + du, v + dv

    # Черноморский циклон — задевает Поти/Батуми/Констанцу
    du, dv = _vortex(
        lat,
        lon,
        (43.2 + 0.7 * math.cos(phase / 2), 35.0 + 2.0 * math.sin(phase / 2)),
        3.0,
        8.0,
        clockwise=False,
    )
    u, v = u + du, v + dv

    # Степной антициклон — спокойная погода над Казахстаном
    du, dv = _vortex(lat, lon, (47.5, 66.0 + 3.0 * math.sin(phase / 3)), 6.0, 4.0, clockwise=True)
    u, v = u + du, v + dv

    # Мелкая текстура, чтобы поле не выглядело стерильным
    u += 1.2 * math.sin(lat * 0.9 + h / 7.0) + 0.8 * math.cos(lon * 0.35)
    v += 1.0 * math.cos(lat * 0.7 - lon * 0.2 + h / 9.0)
    return u, v


def wind_at(lat: float, lon: float, t: datetime) -> tuple[float, float, float]:
    """(устойчивый ветер, порывы, направление «откуда») в точке."""
    u, v = wind_vector(lat, lon, t)
    speed = math.hypot(u, v)
    gust = speed * GUST_FACTOR + GUST_OFFSET
    direction = (math.degrees(math.atan2(u, v)) + 180.0) % 360.0
    return round(speed, 1), round(gust, 1), round(direction)


class MockWindField:
    def __init__(
        self,
        clock: Callable[[], datetime],
        bbox: tuple[float, float, float, float] = DEFAULT_BBOX,
        step_deg: float = DEFAULT_STEP,
    ) -> None:
        self._clock = clock
        self._bbox = bbox
        self._step = step_deg

    async def get_field(
        self, at: datetime | None = None, step_deg: float | None = None
    ) -> WindField | None:
        now = at or self._clock()
        step = step_deg or self._step
        return field_from_points(sea_grid(step, self._bbox)[:MAX_POINTS], step, now)


def field_from_points(
    cells: list[tuple[float, float]], step: float, now: datetime
) -> WindField | None:
    """Поле по узлам сетки (lat, lon) над морем; bbox — по крайним узлам."""
    if not cells:
        return None
    points = [
        WindPoint(lat=lat, lon=lon, speed=speed, gust=gust, dir=direction)
        for lat, lon in cells
        for speed, gust, direction in (wind_at(lat, lon, now),)
    ]
    return WindField(
        ts=now,
        lat_min=min(p.lat for p in points),
        lon_min=min(p.lon for p in points),
        lat_max=max(p.lat for p in points),
        lon_max=max(p.lon for p in points),
        step_deg=step,
        points=points,
    )
