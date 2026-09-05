"""Тесты снимка карты: мок-источники, JSON-API, адаптер боевых источников."""

import re
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
from app.services.corridor import COAST_TOLERANCE_DEG, NODES, NodeKind, sea_at, sea_grid
from app.services.map_snapshot import CorridorStatusAdapter, DbNewsSource, MapSnapshotService
from app.services.status_aggregator import StatusAggregatorService
from app.services.tracking import CheckpointState, PositionSource, ShipmentState, project_shipment
from app.services.weather_predictor import WindThresholds, evaluate_level

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{"mock_data": True, "web_dist_dir": "", **overrides})


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


def test_live_info_reports_mock_time_scale() -> None:
    fast = build_map_service(_settings(mock_time_scale=600), None)
    assert fast.live.time_scale == 600
    assert build_map_service(_settings(), None).live.time_scale == 1.0


async def test_snapshot_carries_codes_and_english_names(mock_service: MapSnapshotService) -> None:
    """Интерфейс на английском строит тексты по кодам, а не по русским строкам."""
    snap = await mock_service.snapshot()
    assert all(n.name_en and n.country_en for n in snap.nodes)
    assert {n.code: n.name_en for n in snap.nodes}["BAKU_ALAT"] == "Baku (Alat)"
    for s in snap.shipments:
        assert s.origin_code in NODES and s.destination_code in NODES
        assert (s.last_event_kind is None) == (s.last_event_at is None)
        if s.last_event_note_code:
            assert s.last_event_note_code in {
                "loaded_on_ferry",
                "loaded_on_vessel",
                "gauge_change_done",
            }
        if s.hold_reason:
            assert s.hold_code, s.ref
    weather = next(s for s in snap.shipments if s.ref == "MC-26-0398")
    assert weather.hold_code == "weather_ban" and weather.hold_node == "AKTAU"
    for v in snap.vessels:
        if v.has_recent_data:
            assert v.from_code in NODES and v.to_code in NODES
            assert v.phase_code in {"at_sea", "in_port"}
            assert (v.phase_code == "in_port") == (v.phase_node is not None)
    assert {r.report_type: r.port_code for r in snap.reports}["queue"] == "AKTAU"


async def test_mock_forecast_and_week_summary(mock_service: MapSnapshotService) -> None:
    snap = await mock_service.snapshot()
    thresholds = WindThresholds.from_settings(_settings())
    ports = [n for n in snap.nodes if n.kind == NodeKind.port]
    for port in ports:
        assert port.forecast is not None and len(port.forecast) == 6 + 48 + 1
        hours = [h.ts for h in port.forecast]
        assert all(
            (b - a).total_seconds() == 3600 for a, b in zip(hours[:-1], hours[1:], strict=True)
        )
        assert hours[0] <= snap.generated_at <= hours[-1]
        for h in port.forecast:
            assert h.level == evaluate_level(h.speed, h.gust, thresholds)
    assert all(n.forecast is None for n in snap.nodes if n.kind != NodeKind.port)

    summary = snap.summary
    assert summary is not None and summary.period_hours == 168
    assert summary.caspian_crossings >= 0
    assert summary.avg_delay_hours is None or summary.avg_delay_hours >= 0
    assert summary.port_downtime_hours is not None and 0 <= summary.port_downtime_hours <= 168 * 5
    assert 0 <= summary.ports_stopped <= len(ports)
    # прогноз и сводка — функция времени: replay даёт то же самое для того же at
    at = snap.generated_at - timedelta(hours=5)
    a, b = await mock_service.snapshot(at=at), await mock_service.snapshot(at=at)
    assert a.summary == b.summary
    assert [n.forecast for n in a.nodes] == [n.forecast for n in b.nodes]
    port_code = ports[0].code
    forecast_at = next(n.forecast for n in a.nodes if n.code == port_code)
    forecast_now = next(n.forecast for n in snap.nodes if n.code == port_code)
    assert forecast_at is not None and forecast_now is not None
    assert forecast_at[0].ts == forecast_now[0].ts - timedelta(hours=5)


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


async def test_mock_wind_field_grid_is_sea_only() -> None:
    field = await MockWindField(lambda: NOW, step_deg=1.0).get_field()
    assert field is not None
    cells = {(p.lat, p.lon) for p in field.points}
    assert (44.0, 50.0) in cells  # Каспий у Актау
    assert (43.0, 36.0) in cells  # Чёрное море
    assert (44.0, 53.0) not in cells  # Мангышлак, суша
    assert (43.0, 77.0) not in cells  # Алматы, далеко за bbox
    assert (42.0, 44.0) not in cells  # Кавказ между морями
    for point in field.points:
        assert sea_at(point.lat, point.lon, COAST_TOLERANCE_DEG) is not None
        assert point.speed >= 0 and point.gust > point.speed and 0 <= point.dir < 360
    # сетка выровнена по кратным шага, bbox — по крайним узлам
    assert all(p.lat == round(p.lat) and p.lon == round(p.lon) for p in field.points)
    assert field.lat_min == min(p.lat for p in field.points)
    # мельче шаг — больше точек, но всё ещё только море
    fine = await MockWindField(lambda: NOW, step_deg=0.5).get_field()
    assert fine is not None and len(fine.points) > 3 * len(field.points)


async def test_mock_shipments_carry_english_cargo(mock_service: MapSnapshotService) -> None:
    snap = await mock_service.snapshot()
    assert snap.shipments and all(s.cargo_en for s in snap.shipments)
    assert all(not re.search("[А-Яа-я]", s.cargo_en or "") for s in snap.shipments)


def test_sea_polygons_cover_ports_and_exclude_land() -> None:
    assert sea_at(43.63, 51.1) == "caspian"  # рейд Актау
    assert sea_at(40.1, 50.0) == "caspian"  # южнее Апшерона, подходы к Баку
    assert sea_at(42.2, 41.5) == "black_sea"  # рейд Поти
    assert sea_at(44.2, 29.0) == "black_sea"  # Констанца
    assert sea_at(41.3, 53.5) is None  # Кара-Богаз-Гол исключён
    assert sea_at(46.5, 34.0) is None  # Азов не считаем
    assert sea_at(51.1, 71.4) is None  # Астана
    assert sea_at(43.65, 51.2) is None  # сам берег Актау — суша без допуска…
    assert sea_at(43.65, 51.2, COAST_TOLERANCE_DEG) == "caspian"  # …и море с ним
    grid = sea_grid(1.0)
    assert 80 < len(grid) < 160
    assert all(sea_at(lat, lon, COAST_TOLERANCE_DEG) for lat, lon in grid)
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
        assert wind.status_code == 200 and len(wind.json()["points"]) > 60

        one = await client.get("/api/v1/shipments/mc-26-0412")
        assert one.status_code == 200 and one.json()["ref"] == "MC-26-0412"
        assert (await client.get("/api/v1/shipments/NOPE")).status_code == 404
        assert (await client.get("/health")).json()["mock"] is True

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


class _DeadNodes:
    """Источник узлов, у которого «упала БД» — как на демо без Postgres."""

    async def list_nodes(self, at=None):  # noqa: ANN001, ANN202
        raise OSError("connection refused")


async def test_unavailable_source_is_503_not_500(mock_service: MapSnapshotService) -> None:
    broken = MapSnapshotService(
        nodes=_DeadNodes(),
        vessels=mock_service._vessels,  # noqa: SLF001
        thresholds=WindThresholds.from_settings(_settings()),
    )
    app = create_app(settings=_settings(mock_data=False), map_service=broken)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/snapshot")
        assert response.status_code == 503
        assert "MOCK_DATA" in response.json()["detail"]
        health = await client.get("/health")
        assert health.json()["mock"] is False and health.json()["db"] is False


async def test_replay_at_is_deterministic_and_windowed(mock_service: MapSnapshotService) -> None:
    app = create_app(settings=_settings(), map_service=mock_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        live = (await client.get("/api/v1/snapshot")).json()
        assert live["replay"] is False and live["live"]["replay_past_hours"] == 72
        at = (datetime.now(UTC) - timedelta(hours=24)).replace(microsecond=0)
        past = await client.get("/api/v1/snapshot", params={"at": at.isoformat()})
        assert past.status_code == 200
        body = past.json()
        assert body["replay"] is True
        assert datetime.fromisoformat(body["generated_at"]) == at
        # тот же момент — тот же снимок; другой момент — другие позиции
        again = (await client.get("/api/v1/snapshot", params={"at": at.isoformat()})).json()
        assert again["shipments"] == body["shipments"]
        assert body["shipments"][2]["position"] != live["shipments"][2]["position"]
        # ветер на момент at и с мелкой сеткой
        wind = await client.get("/api/v1/wind", params={"at": at.isoformat(), "step": 0.5})
        assert wind.status_code == 200 and len(wind.json()["points"]) > 300
        # вне окна — 400 с причиной
        far = datetime.now(UTC) - timedelta(days=10)
        assert (
            await client.get("/api/v1/snapshot", params={"at": far.isoformat()})
        ).status_code == 400


async def test_stream_events_and_availability(mock_service: MapSnapshotService) -> None:
    from app.api.routes.v1 import snapshot_events
    from app.services.map_snapshot import LiveInfo

    live_service = MapSnapshotService(
        nodes=mock_service._nodes,  # noqa: SLF001
        vessels=mock_service._vessels,  # noqa: SLF001
        thresholds=WindThresholds.from_settings(_settings()),
        live=LiveInfo(stream=True, refresh_s=0, replay_past_hours=1, replay_future_hours=1),
    )
    calls = 0

    async def disconnected_after_two() -> bool:
        nonlocal calls
        calls += 1
        return calls > 2

    frames = [frame async for frame in snapshot_events(live_service, disconnected_after_two)]
    assert len(frames) == 2 and all(
        frame.startswith("event: snapshot\ndata: {") for frame in frames
    )

    # Поток выключен (как на Vercel) — 404 с подсказкой про поллинг.
    # На включённом потоке GET не завершается, поэтому тут только выключенный.
    no_stream = build_map_service(_settings(stream_enabled=False), None)
    assert no_stream.live.stream is False and no_stream.live.refresh_s == 10
    app = create_app(settings=_settings(), map_service=no_stream)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/stream")
        assert response.status_code == 404 and "поллинг" in response.json()["detail"]


def test_stream_auto_disabled_on_vercel() -> None:
    assert Settings(_env_file=None).stream_available is True
    assert Settings(_env_file=None, vercel="1").stream_available is False
    assert Settings(_env_file=None, vercel="1", stream_enabled=True).stream_available is True


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
