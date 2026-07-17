"""Доступ к данным погодного модуля: снимки и алерты."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertLevel, Port, WeatherAlert, WeatherSnapshot
from app.integrations.weather.base import WindObservation


class WeatherRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tracked_ports(self) -> Sequence[Port]:
        result = await self._session.execute(
            select(Port).where(Port.is_weather_tracked.is_(True)).order_by(Port.id)
        )
        return result.scalars().all()

    async def add_snapshot(self, port_id: int, obs: WindObservation) -> WeatherSnapshot:
        snapshot = WeatherSnapshot(
            port_id=port_id,
            wind_speed=obs.wind_speed,
            wind_gust=obs.wind_gust,
            wind_dir=obs.wind_dir,
            ts=obs.ts,
            raw=obs.raw,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def get_active_alert(self, port_id: int) -> WeatherAlert | None:
        result = await self._session.execute(
            select(WeatherAlert)
            .where(WeatherAlert.port_id == port_id, WeatherAlert.is_active.is_(True))
            .order_by(WeatherAlert.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def open_alert(
        self, port_id: int, level: AlertLevel, message: str, ts: datetime
    ) -> WeatherAlert:
        alert = WeatherAlert(
            port_id=port_id, level=level, message=message, opened_at=ts, is_active=True
        )
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def close_alert(self, alert: WeatherAlert, ts: datetime) -> None:
        alert.is_active = False
        alert.closed_at = ts
