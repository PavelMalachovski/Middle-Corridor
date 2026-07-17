"""Доступ к данным AIS-модуля: суда, позиции, события портов."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Port, PortEvent, PortEventType, PositionSource, Vessel, VesselPosition
from app.integrations.ais.base import AISPosition


class AISRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def tracked_vessels_with_mmsi(self) -> Sequence[Vessel]:
        result = await self._session.execute(
            select(Vessel).where(Vessel.is_tracked.is_(True), Vessel.mmsi.is_not(None))
        )
        return result.scalars().all()

    async def get_vessel_by_mmsi(self, mmsi: int) -> Vessel | None:
        result = await self._session.execute(select(Vessel).where(Vessel.mmsi == mmsi))
        return result.scalar_one_or_none()

    async def get_port_by_code(self, code: str) -> Port | None:
        result = await self._session.execute(select(Port).where(Port.code == code.upper()))
        return result.scalar_one_or_none()

    async def add_position(
        self, vessel_id: int, position: AISPosition, source: PositionSource
    ) -> VesselPosition:
        row = VesselPosition(
            vessel_id=vessel_id,
            lat=position.lat,
            lon=position.lon,
            sog=position.sog,
            cog=position.cog,
            nav_status=position.nav_status,
            ts=position.ts,
            source=source,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_port_event(
        self,
        port_id: int,
        vessel_id: int,
        event_type: PortEventType,
        ts: datetime,
        source: PositionSource,
    ) -> PortEvent:
        event = PortEvent(
            port_id=port_id, vessel_id=vessel_id, event_type=event_type, ts=ts, source=source
        )
        self._session.add(event)
        await self._session.flush()
        return event
