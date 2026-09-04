"""Поле ветра над регионом — слой для карты.

Сетка точек (lat, lon) с устойчивым ветром, порывами и направлением.
Направление — метеорологическое («откуда дует»), как у Open-Meteo и в
weather_snapshots; фронт разворачивает стрелку на 180° для «куда дует».
"""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class WindPoint(BaseModel):
    lat: float
    lon: float
    speed: float  # м/с
    gust: float  # м/с
    dir: float  # градусы, откуда дует


class WindField(BaseModel):
    ts: datetime
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float
    step_deg: float
    points: list[WindPoint]


class WindFieldSource(Protocol):
    async def get_field(self) -> WindField | None: ...
