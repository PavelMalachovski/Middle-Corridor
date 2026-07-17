"""Агрегатор статуса коридора (§7.5).

Собирает сводную картину: по каждому плечу — погодные алерты и последний
ветер по портам, свежесть AIS-данных по судам (честное «нет данных»),
свежие одобренные ручные сводки. Возвращает pydantic-модель — форматтеры
превращают её в текст для Telegram (и в фазе 2 — в JSON для Mini App).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AlertLevel, CorridorLeg
from app.db.repositories.status import StatusRepository


def _ensure_utc(ts: datetime | None) -> datetime | None:
    """SQLite отдаёт naive datetime — нормализуем к UTC-aware."""
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


class PortStatus(BaseModel):
    code: str
    name: str
    country: str
    leg: CorridorLeg
    alert_level: AlertLevel | None = None
    alert_message: str | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None
    weather_ts: datetime | None = None


class VesselStatus(BaseModel):
    name: str
    operator: str | None = None
    lat: float | None = None
    lon: float | None = None
    sog: float | None = None
    ts: datetime | None = None
    has_recent_data: bool = False  # False = «нет данных», а не «стоит»


class ReportStatus(BaseModel):
    report_type: str
    port_name: str | None = None
    payload: dict[str, Any]
    note: str | None = None
    ts: datetime


class CorridorStatus(BaseModel):
    generated_at: datetime
    ports: list[PortStatus]
    vessels: list[VesselStatus]
    recent_reports: list[ReportStatus]


class StatusAggregatorService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        vessel_stale_after: timedelta = timedelta(hours=6),
        reports_window: timedelta = timedelta(hours=48),
        reports_limit: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._vessel_stale_after = vessel_stale_after
        self._reports_window = reports_window
        self._reports_limit = reports_limit

    async def get_corridor_status(self) -> CorridorStatus:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            repo = StatusRepository(session)
            ports = [await self._port_status(repo, port) for port in await repo.ports()]
            vessels = [
                await self._vessel_status(repo, vessel, now)
                for vessel in await repo.tracked_vessels()
            ]
            reports = [
                ReportStatus(
                    report_type=report.report_type.value,
                    port_name=report.port.name if report.port is not None else None,
                    payload=report.payload,
                    note=report.note,
                    ts=_ensure_utc(report.ts),  # type: ignore[arg-type]
                )
                for report in await repo.recent_published_reports(
                    since=now - self._reports_window, limit=self._reports_limit
                )
            ]
        return CorridorStatus(
            generated_at=now, ports=ports, vessels=vessels, recent_reports=reports
        )

    async def get_port_status(self, query: str) -> PortStatus | None:
        """Поиск порта по коду (AKTAU) или подстроке имени («актау»)."""
        needle = query.strip().lower()
        async with self._session_factory() as session:
            repo = StatusRepository(session)
            for port in await repo.ports():
                if port.code.lower() == needle or needle in port.name.lower():
                    return await self._port_status(repo, port)
        return None

    async def _port_status(self, repo: StatusRepository, port) -> PortStatus:
        snapshot = await repo.latest_snapshot(port.id)
        alert = await repo.active_alert(port.id)
        return PortStatus(
            code=port.code,
            name=port.name,
            country=port.country,
            leg=port.leg,
            alert_level=alert.level if alert is not None else None,
            alert_message=alert.message if alert is not None else None,
            wind_speed=snapshot.wind_speed if snapshot is not None else None,
            wind_gust=snapshot.wind_gust if snapshot is not None else None,
            weather_ts=_ensure_utc(snapshot.ts) if snapshot is not None else None,
        )

    async def _vessel_status(self, repo: StatusRepository, vessel, now: datetime) -> VesselStatus:
        position = await repo.latest_position(vessel.id)
        ts = _ensure_utc(position.ts) if position is not None else None
        has_recent = ts is not None and now - ts < self._vessel_stale_after
        return VesselStatus(
            name=vessel.name,
            operator=vessel.operator,
            lat=position.lat if position is not None else None,
            lon=position.lon if position is not None else None,
            sog=position.sog if position is not None else None,
            ts=ts,
            has_recent_data=has_recent,
        )
