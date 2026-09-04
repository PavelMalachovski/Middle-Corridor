"""Тесты снимка карты: мок-источники, JSON-API, адаптер боевых источников."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from app.db.models import CorridorLeg, NewsItem, Port, Vessel, WeatherSnapshot
from app.integrations.mock.clock import MockClock
from app.integrations.mock.fleet import FERRIES, MockShipmentSource, list_ferry_states
from app.integrations.mock.wind import MockWindField, wind_at
from app.main import build_map_service
from app.services.corridor import NODES, NodeKind
from app.services.map_snapshot import CorridorStatusAdapter, DbNewsSource, MapSnapshotService
from app.services.status_aggregator import StatusAggregatorService
from app.services.tracking import CheckpointState, PositionSource, ShipmentState, project_shipment
from app.services.weather_predictor import WindThresholds, evaluate_level

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, mock_data=True, web_dist_dir="", **overrides)


@pytest.fixture
def mock_service() -> MapSnapshotService:
    return build_map_service(_settings(), None)


async def test_mock_snapshot_is_internally_consistent(mock_service: MapSnapshotService) -> None:
    snap = await mock_service.snapshot()
    assert snap.mock is True
    thresholds = WindThresholds.from_settings(_settings())

    ports = [n for n in snap.nodes if n.kind == NodeKind.port]
    assert {p.code for p in ports} == {c for c, n in NODES.items() if n.kind == NodeKind.port}
    for port in ports:
        assert port.is_weather_tracked and port.wind_speed is not None
        assert port.alert_level == evaluate_level(port.wind_speed, port.wind_gust, thresholds)
        assert (port.alert_message is not None) == (port.alert_level is not None)
    rail = [n for n in snap.nodes if n.kind != NodeKind.port]
    assert rail and all(n.wind_speed is None and n.alert_level is None for n in rail)

    by_name = {v.name: v for v in snap.vessels}
    assert set(by_name) == {spec.name for spec in FERRIES}
    for spec in FERRIES:
        vessel = by_name[spec.name]
        if spec.has_ais:
            assert vessel.has_recent_data and vessel.lat is not None and vessel.route
        else:  # честное «нет данных»
            assert not vessel.has_recent_data and vessel.lat is None and vessel.route is None

    assert len(snap.shipments) >= 8
    assert len({s.ref for s in snap.shipments}) == len(snap.shipments)
    states = {s.state for s in snap.shipments}
    assert {ShipmentState.in_transit, ShipmentState.waiting, ShipmentState.delivered} <= states
    for shipment in snap.shipments:
        assert len(shipment.track) >= 2 and len(shipment.checkpoints) >= 2
        current = [cp for cp in shipment.checkpoints if cp.state == CheckpointState.current]
        if shipment.state == ShipmentState.delivered:
            assert not current
        else:
            assert len(current) == 1
        if shipment.position.source == PositionSource.ais:
            vessel = by_name[shipment.position.on_vessel]
            assert (shipment.position.lat, shipment.position.lon) == (vessel.lat, vessel.lon)
    on_ferry = next(s for s in snap.shipments if s.position.source == PositionSource.ais)
    assert on_ferry.state == ShipmentState.in_transit and on_ferry.position.mode == "sea"
    weather_hold = next(s for s in snap.shipments if s.ref == "MC-26-0398")
    assert weather_hold.state == ShipmentState.waiting and weather_hold.delay_hours >= 18

    assert snap.segments and snap.news and snap.reports
    assert snap.thresholds.critical_wind == thresholds.critical_wind


async def test_mock_shipments_move_with_time() -> None:
    plans = await MockShipmentSource(lambda: NOW).list_plans()
    steppe = next(p for p in plans if p.ref == "MC-26-0431")
    before = project_shipment(steppe, NOW).position
    after = project_shipment(steppe, NOW + timedelta(hours=2)).position
    assert before.source == PositionSource.projection
    assert (before.lat, before.lon) != (after.lat, after.lon)
    assert after.leg_progress > before.leg_progress


def test_ferry_cycle_always_has_westbound_ais_ferry() -> None:
    for hour in range(0, 60, 3):
        states = list_ferry_states(NOW + timedelta(hours=hour))
        assert any(s.sailing and s.westbound and s.spec.has_ais for s in states), hour


async def test_mock_wind_field_grid() -> None:
    field = await MockWindField(
        lambda: NOW, bbox=(40.0, 48.0, 46.0, 54.0), step_deg=2.0
    ).get_field()
    assert field is not None
    assert len(field.points) == 4 * 4
    for point in field.points:
        assert 40.0 <= point.lat <= 46.0 and 48.0 <= point.lon <= 54.0
        assert point.speed >= 0 and point.gust > point.speed and 0 <= point.dir < 360
    # детерминированность по времени
    assert wind_at(43.63, 51.25, NOW) == wind_at(43.63, 51.25, NOW)
    assert wind_at(43.63, 51.25, NOW) != wind_at(43.63, 51.25, NOW + timedelta(hours=6))


def test_mock_clock_scales_time() -> None:
    anchor = datetime.now(UTC)
    clock = MockClock(scale=60.0, anchor=anchor - timedelta(seconds=10))
    assert clock.now() - anchor >= timedelta(minutes=9, seconds=50)


async def test_api_endpoints(mock_service: MapSnapshotService) -> None:
    app = create_app(settings=_settings(), map_service=mock_service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        snapshot = await client.get("/api/v1/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.headers["cache-control"] == "no-store"
        body = snapshot.json()
        assert body["mock"] is True
        assert {"nodes", "vessels", "shipments", "segments", "news", "reports"} <= body.keys()
        assert body["shipments"][0]["track"][0] == [NODES["XIAN"].lon, NODES["XIAN"].lat]

        wind = await client.get("/api/v1/wind")
        assert wind.status_code == 200 and len(wind.json()["points"]) > 100

        one = await client.get("/api/v1/shipments/mc-26-0412")
        assert one.status_code == 200 and one.json()["ref"] == "MC-26-0412"
        assert (await client.get("/api/v1/shipments/NOPE")).status_code == 404

    bare = create_app(settings=_settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bare), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/snapshot")).status_code == 503


async def test_cors_enabled_only_with_origins(mock_service: MapSnapshotService) -> None:
    app = create_app(
        settings=_settings(cors_origins=["https://mc.vercel.app"]), map_service=mock_service
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        allowed = await client.get("/api/v1/snapshot", headers={"Origin": "https://mc.vercel.app"})
        assert allowed.headers.get("access-control-allow-origin") == "https://mc.vercel.app"
        other = await client.get("/api/v1/snapshot", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers

    plain = create_app(settings=_settings(), map_service=mock_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=plain), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/snapshot", headers={"Origin": "https://mc.vercel.app"})
        assert "access-control-allow-origin" not in response.headers


def test_real_mode_requires_db() -> None:
    with pytest.raises(ValueError):
        build_map_service(Settings(_env_file=None, mock_data=False), None)


async def test_real_sources_adapter(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    aktau = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
    )
    session.add_all([aktau, Vessel(mmsi=None, name="Barda", operator="ASCO")])
    await session.flush()
    session.add(
        WeatherSnapshot(port_id=aktau.id, wind_speed=9.0, wind_gust=12.0, wind_dir=200.0, ts=NOW)
    )
    session.add_all(
        [
            NewsItem(
                source="s", url="https://x/1", title="old", published_at=NOW - timedelta(days=2)
            ),
            NewsItem(
                source="s", url="https://x/2", title="new", title_ru="новое", published_at=NOW
            ),
        ]
    )
    await session.commit()

    adapter = CorridorStatusAdapter(StatusAggregatorService(session_factory))
    nodes = {n.code: n for n in await adapter.list_nodes()}
    assert nodes["AKTAU"].wind_speed == 9.0 and nodes["AKTAU"].wind_dir == 200.0
    assert nodes["AKTAU"].kind == NodeKind.port and nodes["AKTAU"].is_weather_tracked
    assert "KHORGOS" in nodes and nodes["KHORGOS"].wind_speed is None  # статический узел
    vessels = await adapter.list_vessels()
    assert vessels[0].name == "Barda" and not vessels[0].has_recent_data

    news = await DbNewsSource(session_factory).list_news(limit=10)
    assert [n.title for n in news] == ["новое", "old"]  # перевод в приоритете, свежие первыми

    service = MapSnapshotService(
        nodes=adapter,
        vessels=adapter,
        reports=adapter,
        news=DbNewsSource(session_factory),
        thresholds=WindThresholds.from_settings(Settings(_env_file=None)),
    )
    snap = await service.snapshot()
    assert snap.mock is False and snap.shipments == [] and await service.wind() is None
