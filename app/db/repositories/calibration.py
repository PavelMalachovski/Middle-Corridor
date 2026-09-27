"""Доступ к данным калибровки: журнал остановок, алерты и ветер за период."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AlertLevel,
    ClosureCause,
    Port,
    PortClosure,
    WeatherAlert,
    WeatherSnapshot,
)
from app.integrations.weather.base import WindObservation


class CalibrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_port(self, query: str) -> Port | None:
        """Порт по коду (AKTAU) или подстроке имени («актау») — как в /status."""
        needle = query.strip().lower()
        if not needle:
            return None
        for port in (await self._session.execute(select(Port).order_by(Port.id))).scalars():
            if port.code.lower() == needle or needle in port.name.lower():
                return port
        return None

    async def tracked_ports(self) -> Sequence[Port]:
        result = await self._session.execute(
            select(Port).where(Port.is_weather_tracked.is_(True)).order_by(Port.id)
        )
        return result.scalars().all()

    async def open_closure(self, port_id: int) -> PortClosure | None:
        result = await self._session.execute(
            select(PortClosure)
            .where(PortClosure.port_id == port_id, PortClosure.ended_at.is_(None))
            .order_by(PortClosure.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_closure(
        self,
        port_id: int,
        started_at: datetime,
        ended_at: datetime | None,
        cause: ClosureCause,
        note: str | None,
        reported_by: int | None,
    ) -> PortClosure:
        closure = PortClosure(
            port_id=port_id,
            started_at=started_at,
            ended_at=ended_at,
            cause=cause,
            note=note,
            reported_by=reported_by,
        )
        self._session.add(closure)
        await self._session.flush()
        return closure

    async def closures(
        self, port_id: int, since: datetime, until: datetime, cause: ClosureCause | None = None
    ) -> Sequence[PortClosure]:
        """Остановки, пересекающие [since, until] (в том числе ещё не закончившиеся)."""
        query = select(PortClosure).where(
            PortClosure.port_id == port_id,
            PortClosure.started_at <= until,
            or_(PortClosure.ended_at.is_(None), PortClosure.ended_at >= since),
        )
        if cause is not None:
            query = query.where(PortClosure.cause == cause)
        result = await self._session.execute(query.order_by(PortClosure.started_at))
        return result.scalars().all()

    async def alerts(
        self, port_id: int, since: datetime, until: datetime, levels: Iterable[AlertLevel]
    ) -> Sequence[WeatherAlert]:
        """Алерты заданных уровней, пересекающие [since, until]."""
        result = await self._session.execute(
            select(WeatherAlert)
            .where(
                WeatherAlert.port_id == port_id,
                WeatherAlert.level.in_(list(levels)),
                WeatherAlert.opened_at <= until,
                or_(WeatherAlert.closed_at.is_(None), WeatherAlert.closed_at >= since),
            )
            .order_by(WeatherAlert.opened_at)
        )
        return result.scalars().all()

    async def snapshots(
        self, port_id: int, since: datetime, until: datetime
    ) -> Sequence[WeatherSnapshot]:
        result = await self._session.execute(
            select(WeatherSnapshot)
            .where(
                WeatherSnapshot.port_id == port_id,
                WeatherSnapshot.ts >= since,
                WeatherSnapshot.ts <= until,
            )
            .order_by(WeatherSnapshot.ts)
        )
        return result.scalars().all()

    async def snapshot_times(self, port_id: int, since: datetime, until: datetime) -> set[datetime]:
        result = await self._session.execute(
            select(WeatherSnapshot.ts).where(
                WeatherSnapshot.port_id == port_id,
                WeatherSnapshot.ts >= since,
                WeatherSnapshot.ts <= until,
            )
        )
        return set(result.scalars().all())

    async def add_snapshots(
        self, port_id: int, observations: Iterable[WindObservation], source: str
    ) -> int:
        """Исторический ветер (бэкфилл). raw — только метка источника, не весь ответ."""
        count = 0
        for obs in observations:
            self._session.add(
                WeatherSnapshot(
                    port_id=port_id,
                    wind_speed=obs.wind_speed,
                    wind_gust=obs.wind_gust,
                    wind_dir=obs.wind_dir,
                    ts=obs.ts,
                    raw={"source": source},
                )
            )
            count += 1
        await self._session.flush()
        return count
