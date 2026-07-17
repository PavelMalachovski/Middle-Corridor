"""Доступ к данным для сводного статуса коридора."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ManualReport,
    Port,
    Vessel,
    VesselPosition,
    WeatherAlert,
    WeatherSnapshot,
)


class StatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ports(self) -> Sequence[Port]:
        result = await self._session.execute(select(Port).order_by(Port.id))
        return result.scalars().all()

    async def latest_snapshot(self, port_id: int) -> WeatherSnapshot | None:
        result = await self._session.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.port_id == port_id)
            .order_by(WeatherSnapshot.ts.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def active_alert(self, port_id: int) -> WeatherAlert | None:
        result = await self._session.execute(
            select(WeatherAlert)
            .where(WeatherAlert.port_id == port_id, WeatherAlert.is_active.is_(True))
            .order_by(WeatherAlert.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def tracked_vessels(self) -> Sequence[Vessel]:
        result = await self._session.execute(
            select(Vessel).where(Vessel.is_tracked.is_(True)).order_by(Vessel.name)
        )
        return result.scalars().all()

    async def latest_position(self, vessel_id: int) -> VesselPosition | None:
        result = await self._session.execute(
            select(VesselPosition)
            .where(VesselPosition.vessel_id == vessel_id)
            .order_by(VesselPosition.ts.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def recent_published_reports(self, since: datetime, limit: int) -> Sequence[ManualReport]:
        result = await self._session.execute(
            select(ManualReport)
            .where(ManualReport.is_published.is_(True), ManualReport.ts >= since)
            .options(selectinload(ManualReport.port))
            .order_by(ManualReport.ts.desc())
            .limit(limit)
        )
        return result.scalars().all()
