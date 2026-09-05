"""Боевое поле ветра над морями: Open-Meteo по сетке, история снимков в БД.

Джоба refresh_once раз в WIND_GRID_REFRESH_MINUTES берёт почасовой прогноз
на WIND_GRID_FORECAST_HOURS вперёд во всех узлах sea_grid(step) и кладёт
одной строкой в wind_grids. Источник карты get_field выбирает строку по at:
последнюю из взятых не позже at (прошлое — из истории, будущее — прогноз из
свежей) и ближайший час внутри неё. Так replay работает и на боевых данных:
строка = снимок прогноза на момент взятия, отдельный индекс не нужен.

Каждая точка сетки — отдельный вызов в лимитах Open-Meteo (10 000 в сутки
бесплатно): 0.5° над Каспием и Чёрным морем ≈ 400 точек, обновление раз в
3 часа ≈ 3 200 вызовов в сутки плюс порты предиктора.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import WindGrid
from app.db.repositories.wind_grid import WindGridRepository
from app.integrations.weather.base import WindGridProvider
from app.services.corridor import sea_grid
from app.services.wind_field import WindField, WindPoint

logger = structlog.get_logger(__name__)

# Час прогноза считается подходящим для at, если он не дальше этого
MAX_HOUR_DISTANCE = timedelta(minutes=90)


class WindGridService:
    """WindFieldSource для боевого режима + джоба обновления."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: WindGridProvider | None,
        *,
        step_deg: float = 0.5,
        forecast_hours: int = 48,
        refresh_minutes: int = 180,
        history_hours: int = 96,
        lazy_refresh: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._step = step_deg
        self._forecast_hours = forecast_hours
        self._refresh = timedelta(minutes=refresh_minutes)
        self._history = timedelta(hours=history_hours)
        self._lazy = lazy_refresh
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = asyncio.Lock()

    # --- джоба ------------------------------------------------------------------------

    async def refresh_once(self) -> int:
        """Взять прогноз по всей сетке и сохранить снимком; вернуть число точек."""
        if self._provider is None:
            return 0
        cells = sea_grid(self._step)
        forecasts = await self._provider.get_wind_grid(cells, self._forecast_hours)
        hours: list[datetime] = sorted({h.ts for f in forecasts for h in f.hours})
        if not hours:
            logger.warning("wind_grid_empty", points=len(cells))
            return 0
        index = {ts: i for i, ts in enumerate(hours)}
        points: list[dict[str, Any]] = []
        for f in forecasts:
            speed: list[float | None] = [None] * len(hours)
            gust: list[float | None] = [None] * len(hours)
            direction: list[float | None] = [None] * len(hours)
            for h in f.hours:
                i = index[h.ts]
                speed[i], gust[i], direction[i] = (
                    round(h.wind_speed, 1),
                    round(h.wind_gust, 1),
                    round(h.wind_dir),
                )
            points.append({"lat": f.lat, "lon": f.lon, "s": speed, "g": gust, "d": direction})
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            repo = WindGridRepository(session)
            await repo.add(now, self._step, [h.isoformat() for h in hours], points)
            removed = await repo.delete_older_than(now - self._history)
        logger.info(
            "wind_grid_refreshed", points=len(points), hours=len(hours), removed_rows=removed
        )
        return len(points)

    # --- источник для карты ---------------------------------------------------------------

    async def get_field(
        self, at: datetime | None = None, step_deg: float | None = None
    ) -> WindField | None:
        now = self._clock()
        target = at or now
        row = await self._pick_row(target)
        if row is None or (at is None and self._is_stale(row, now)):
            if await self._maybe_refresh(now):
                row = await self._pick_row(target)
        if row is None:
            return None
        return field_from_row(row, target, step_deg)

    async def _pick_row(self, target: datetime) -> WindGrid | None:
        async with self._session_factory() as session:
            repo = WindGridRepository(session)
            row = await repo.latest(before=target)
            if row is None:
                # at раньше первого снимка: первый снимок ещё может покрывать этот час
                row = await repo.earliest()
            return row

    def _is_stale(self, row: WindGrid, now: datetime) -> bool:
        fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
        return now - fetched > self._refresh * 1.5

    async def _maybe_refresh(self, now: datetime) -> bool:
        """Ленивое обновление (serverless без планировщика): один раз на запрос-стампид."""
        if not self._lazy or self._provider is None:
            return False
        async with self._lock:
            async with self._session_factory() as session:
                latest = await WindGridRepository(session).latest()
            if latest is not None and not self._is_stale(latest, now):
                return True  # кто-то обновил, пока ждали
            try:
                await self.refresh_once()
            except Exception as exc:  # noqa: BLE001 — карта без ветра лучше, чем 500
                logger.warning("wind_grid_lazy_refresh_failed", error=str(exc))
                return latest is not None
            return True


def field_from_row(
    row: WindGrid, target: datetime, step_deg: float | None = None
) -> WindField | None:
    """Поле на ближайший к target час снимка; step_deg грубее шага снимка — прореживание."""
    hours = [datetime.fromisoformat(h) for h in row.hours]
    if not hours:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    i = min(range(len(hours)), key=lambda k: abs(hours[k] - target))
    if abs(hours[i] - target) > MAX_HOUR_DISTANCE:
        return None
    step = row.step_deg
    keep_every = 1
    if step_deg is not None and step_deg > step + 1e-9:
        keep_every = max(1, round(step_deg / step))
        step = step * keep_every
    points: list[WindPoint] = []
    for p in row.points:
        speed, gust, direction = p["s"][i], p["g"][i], p["d"][i]
        if speed is None or gust is None:
            continue
        if keep_every > 1 and not _on_coarse_grid(p["lat"], p["lon"], step):
            continue
        points.append(
            WindPoint(lat=p["lat"], lon=p["lon"], speed=speed, gust=gust, dir=direction or 0.0)
        )
    if not points:
        return None
    return WindField(
        ts=hours[i],
        lat_min=min(p.lat for p in points),
        lon_min=min(p.lon for p in points),
        lat_max=max(p.lat for p in points),
        lon_max=max(p.lon for p in points),
        step_deg=step,
        points=points,
    )


def _on_coarse_grid(lat: float, lon: float, step: float) -> bool:
    return abs(lat / step - round(lat / step)) < 1e-6 and abs(lon / step - round(lon / step)) < 1e-6
