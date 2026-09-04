"""Снимок коридора для карты (веб-приложение, фаза 2).

Собирает в один JSON всё, что рисует фронт: узлы с погодой и алертами,
суда, отправки с проекцией положения, геометрию маршрута, новости и ручные
сводки. Источники — Protocol'ы: в проде это агрегатор статуса и БД, в
прототипе — синтетика из integrations/mock. Сервис не знает, кто за ним.
"""

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AlertLevel, CorridorLeg
from app.db.repositories.news import NewsRepository
from app.services.corridor import NODES, SEGMENTS, NodeKind, TransportMode
from app.services.status_aggregator import CorridorStatus, ReportStatus
from app.services.tracking import Shipment, ShipmentSource, project_shipment
from app.services.weather_predictor import WindThresholds
from app.services.wind_field import WindField, WindFieldSource

# --- Модели ответа -------------------------------------------------------------


class NodeStatus(BaseModel):
    code: str
    name: str
    country: str
    leg: CorridorLeg
    kind: NodeKind
    lat: float
    lon: float
    is_weather_tracked: bool = False
    alert_level: AlertLevel | None = None
    alert_message: str | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None
    wind_dir: float | None = None
    weather_ts: datetime | None = None


class VesselMapStatus(BaseModel):
    name: str
    operator: str | None = None
    mmsi: int | None = None
    lat: float | None = None
    lon: float | None = None
    sog: float | None = None  # узлы
    cog: float | None = None  # градусы
    ts: datetime | None = None
    has_recent_data: bool = False  # False = «нет данных», а не «стоит»
    route: str | None = None  # «Курык → Алят»
    phase: str | None = None  # «в море», «в порту Алят»


class NewsSummary(BaseModel):
    id: int
    source: str
    title: str
    summary: str | None = None
    url: str
    published_at: datetime | None = None


class RouteSegment(BaseModel):
    from_code: str
    to_code: str
    mode: TransportMode
    coordinates: list[list[float]]  # [lon, lat]


class ThresholdsOut(BaseModel):
    watch_wind: float
    warning_wind: float
    warning_gust: float
    critical_wind: float
    critical_gust: float


class LiveInfo(BaseModel):
    """Как фронту получать обновления: поток SSE или поллинг с интервалом."""

    stream: bool
    refresh_s: int
    replay_past_hours: int
    replay_future_hours: int


class MapSnapshot(BaseModel):
    generated_at: datetime  # момент, на который построен снимок (при replay — запрошенный at)
    server_time: datetime  # реальное «сейчас» сервера
    replay: bool  # снимок на прошлое/будущее, а не живой
    mock: bool
    live: LiveInfo
    nodes: list[NodeStatus]
    vessels: list[VesselMapStatus]
    shipments: list[Shipment]
    segments: list[RouteSegment]
    news: list[NewsSummary]
    reports: list[ReportStatus]
    thresholds: ThresholdsOut


# --- Интерфейсы источников -----------------------------------------------------


# at — момент, на который нужны данные (None = сейчас). Мок считает любой
# момент, боевые источники пока отдают текущее состояние и игнорируют at.


class NodeSource(Protocol):
    async def list_nodes(self, at: datetime | None = None) -> list[NodeStatus]: ...


class VesselSource(Protocol):
    async def list_vessels(self, at: datetime | None = None) -> list[VesselMapStatus]: ...


class ReportSource(Protocol):
    async def list_reports(self, at: datetime | None = None) -> list[ReportStatus]: ...


class NewsSource(Protocol):
    async def list_news(self, limit: int, at: datetime | None = None) -> list[NewsSummary]: ...


def static_segments() -> list[RouteSegment]:
    return [
        RouteSegment(
            from_code=seg.from_code,
            to_code=seg.to_code,
            mode=seg.mode,
            coordinates=[[lon, lat] for lat, lon in seg.points],
        )
        for seg in SEGMENTS.values()
    ]


class MapSnapshotService:
    def __init__(
        self,
        *,
        nodes: NodeSource,
        vessels: VesselSource,
        thresholds: WindThresholds,
        shipments: ShipmentSource | None = None,
        wind: WindFieldSource | None = None,
        news: NewsSource | None = None,
        reports: ReportSource | None = None,
        mock: bool = False,
        news_limit: int = 20,
        clock: Callable[[], datetime] | None = None,
        live: LiveInfo | None = None,
    ) -> None:
        self._nodes = nodes
        self._vessels = vessels
        self._shipments = shipments
        self._wind = wind
        self._news = news
        self._reports = reports
        self._thresholds = thresholds
        self._mock = mock
        self._news_limit = news_limit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._live = live or LiveInfo(
            stream=False, refresh_s=10, replay_past_hours=72, replay_future_hours=24
        )

    @property
    def live(self) -> LiveInfo:
        return self._live

    def now(self) -> datetime:
        return self._clock()

    def check_replay_window(self, at: datetime) -> None:
        """at должен лежать в окне replay относительно «сейчас», иначе ValueError."""
        now = self._clock()
        lo = now - timedelta(hours=self._live.replay_past_hours)
        hi = now + timedelta(hours=self._live.replay_future_hours)
        if not lo <= at <= hi:
            raise ValueError(f"at вне окна replay: от {lo:%Y-%m-%dT%H:%M}Z до {hi:%Y-%m-%dT%H:%M}Z")

    async def snapshot(self, at: datetime | None = None) -> MapSnapshot:
        """Снимок на момент at; None — живой снимок на «сейчас»."""
        server_time = self._clock()
        now = at or server_time
        vessels = await self._vessels.list_vessels(at)
        shipments = await self._project_shipments(vessels, now, at)
        return MapSnapshot(
            generated_at=now,
            server_time=server_time,
            replay=at is not None,
            mock=self._mock,
            live=self._live,
            nodes=await self._nodes.list_nodes(at),
            vessels=vessels,
            shipments=shipments,
            segments=static_segments(),
            news=await self._news.list_news(self._news_limit, at) if self._news else [],
            reports=await self._reports.list_reports(at) if self._reports else [],
            thresholds=ThresholdsOut(**dataclasses.asdict(self._thresholds)),
        )

    async def wind(
        self, at: datetime | None = None, step_deg: float | None = None
    ) -> WindField | None:
        if self._wind is None:
            return None
        return await self._wind.get_field(at, step_deg)

    async def shipment(self, ref: str, at: datetime | None = None) -> Shipment | None:
        now = at or self._clock()
        vessels = await self._vessels.list_vessels(at)
        for shipment in await self._project_shipments(vessels, now, at):
            if shipment.ref.lower() == ref.strip().lower():
                return shipment
        return None

    async def _project_shipments(
        self, vessels: list[VesselMapStatus], now: datetime, at: datetime | None
    ) -> list[Shipment]:
        if self._shipments is None:
            return []
        known = {
            v.name: (v.lat, v.lon)
            for v in vessels
            if v.has_recent_data and v.lat is not None and v.lon is not None
        }
        plans = await self._shipments.list_plans(at)
        return [project_shipment(plan, now, known) for plan in plans]


# --- Боевые источники: агрегатор статуса и БД ---------------------------------


class StatusSourceProto(Protocol):
    async def get_corridor_status(self) -> CorridorStatus: ...


class CorridorStatusAdapter:
    """Порты/суда/сводки из StatusAggregatorService + статические узлы рельсов.

    Порты берутся из БД (сиды миграции), у них есть погода и алерты; узлы
    без погоды (ж/д, границы) — из справочника corridor.py.
    """

    def __init__(self, status: StatusSourceProto) -> None:
        self._status = status

    async def list_nodes(self, at: datetime | None = None) -> list[NodeStatus]:
        status = await self._status.get_corridor_status()
        db_codes = {port.code for port in status.ports}
        nodes = [
            NodeStatus(
                code=port.code,
                name=port.name,
                country=port.country,
                leg=port.leg,
                kind=NodeKind.port,
                lat=port.lat,
                lon=port.lon,
                is_weather_tracked=True,
                alert_level=port.alert_level,
                alert_message=port.alert_message,
                wind_speed=port.wind_speed,
                wind_gust=port.wind_gust,
                wind_dir=port.wind_dir,
                weather_ts=port.weather_ts,
            )
            for port in status.ports
        ]
        nodes.extend(
            NodeStatus(
                code=node.code,
                name=node.name,
                country=node.country,
                leg=node.leg,
                kind=node.kind,
                lat=node.lat,
                lon=node.lon,
            )
            for node in NODES.values()
            if node.code not in db_codes
        )
        return nodes

    async def list_vessels(self, at: datetime | None = None) -> list[VesselMapStatus]:
        status = await self._status.get_corridor_status()
        return [
            VesselMapStatus(
                name=v.name,
                operator=v.operator,
                lat=v.lat,
                lon=v.lon,
                sog=v.sog,
                ts=v.ts,
                has_recent_data=v.has_recent_data,
            )
            for v in status.vessels
        ]

    async def list_reports(self, at: datetime | None = None) -> list[ReportStatus]:
        return (await self._status.get_corridor_status()).recent_reports


class DbNewsSource:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_news(self, limit: int, at: datetime | None = None) -> list[NewsSummary]:
        async with self._session_factory() as session:
            items = await NewsRepository(session).list_recent(limit)
            return [
                NewsSummary(
                    id=item.id,
                    source=item.source,
                    title=item.title_ru or item.title,
                    summary=item.summary_ru or item.summary,
                    url=item.url,
                    published_at=item.published_at,
                )
                for item in items
            ]
