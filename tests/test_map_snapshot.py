"""Тесты снимка карты: мок-источники, JSON-API, адаптер боевых источников."""

import dataclasses
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from app.db.models import CorridorLeg, NewsItem, Port, Vessel, WeatherSnapshot
from app.integrations.mock.clock import MockClock
from app.integrations.mock.fleet import (
    EAST_FERRY,
    FERRIES,
    ROUTE_KOSTANAY,
    ROUTE_KURYK,
    MockShipmentSource,
    build_plan,
    east_departure,
    east_plan,
    list_ferry_states,
)
from app.integrations.mock.wind import MockWindField, wind_at
from app.main import build_map_service
from app.services.corridor import COAST_TOLERANCE_DEG, NODES, NodeKind, sea_at, sea_grid
from app.services.map_snapshot import CorridorStatusAdapter, DbNewsSource, MapSnapshotService
from app.services.queue_forecast import QueueInput
from app.services.sanctions import PackingLine, PackingList
from app.services.status_aggregator import CorridorStatus, StatusAggregatorService
from app.services.tracking import (
    CheckpointState,
    EventKind,
    PositionSource,
    Shipment,
    ShipmentState,
    project_shipment,
)
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

    # публичное демо — ровно два груза: восточный 0501 и пример санкционки 0431
    assert [s.ref for s in snap.shipments] == ["MC-26-0501", "MC-26-0431"]
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
    east, steppe = snap.shipments
    # 0501 опаздывает всегда (в демо есть груз «с задержкой»), 0431 идёт по плану
    assert east.state in {ShipmentState.in_transit, ShipmentState.waiting}
    assert east.delay_hours >= 10
    assert steppe.state == ShipmentState.in_transit and steppe.delay_hours < 1

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
    east = next(s for s in snap.shipments if s.ref == "MC-26-0501")
    if east.position.from_code == "BAKU_ALAT" and east.state == ShipmentState.waiting:
        assert east.hold_code in {"ferry_loading_wait", "ferry_return_wait"}
        assert east.hold_vessel == EAST_FERRY
    else:  # после Алята — ни стоянки по парому, ни очереди
        assert east.hold_code is None and east.queue is None
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
        origin = NODES["MLADA_BOLESLAV"]
        assert body["shipments"][0]["track"][0] == [origin.lon, origin.lat]

        wind = await client.get("/api/v1/wind")
        assert wind.status_code == 200 and len(wind.json()["points"]) > 60

        one = await client.get("/api/v1/shipments/mc-26-0501")
        assert one.status_code == 200 and one.json()["ref"] == "MC-26-0501"
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
        assert body["shipments"][1]["position"] != live["shipments"][1]["position"]
        assert [v["lat"] for v in body["vessels"]] != [v["lat"] for v in live["vessels"]]
        # ветер на момент at и с мелкой сеткой
        wind = await client.get("/api/v1/wind", params={"at": at.isoformat(), "step": 0.5})
        assert wind.status_code == 200 and len(wind.json()["points"]) > 300
        # вне окна — 400 с причиной
        far = datetime.now(UTC) - timedelta(days=10)
        assert (
            await client.get("/api/v1/snapshot", params={"at": far.isoformat()})
        ).status_code == 400


async def test_replay_at_out_of_datetime_range_is_400(mock_service: MapSnapshotService) -> None:
    app = create_app(settings=_settings(), map_service=mock_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for at in ("9999-12-31T23:59:59-14:00", "0001-01-01T00:00:00+14:00"):
            response = await client.get("/api/v1/snapshot", params={"at": at})
            assert response.status_code == 400, at  # в UTC не влезает в datetime — не 500


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


class _CountingStatus:
    def __init__(self) -> None:
        self.calls = 0

    async def get_corridor_status(self) -> CorridorStatus:
        self.calls += 1
        return CorridorStatus(generated_at=NOW, ports=[], vessels=[], recent_reports=[])


async def test_adapter_hits_aggregator_once_per_snapshot() -> None:
    """Узлы, суда и сводки одного снимка — один проход агрегатора, а не три."""
    status = _CountingStatus()
    clock = [100.0]
    adapter = CorridorStatusAdapter(status, ttl_s=2.0, monotonic=lambda: clock[0])
    service = MapSnapshotService(
        nodes=adapter,
        vessels=adapter,
        reports=adapter,
        thresholds=WindThresholds.from_settings(_settings()),
    )
    await service.snapshot()
    assert status.calls == 1
    await adapter.list_nodes()
    assert status.calls == 1  # в пределах TTL — из кеша
    clock[0] += 2.5
    await adapter.list_vessels()
    assert status.calls == 2  # TTL истёк — свежий статус


def test_mock_build_plan_weather_queue() -> None:
    """Груз ждёт в Актау под погодным запретом: build_plan с очередью даёт прогноз выхода."""
    plan = build_plan(
        "T-Q",
        "c",
        "1 × 40' HC, автозапчасти",
        ROUTE_KURYK[:7] + ["AKTAU", "BAKU_ALAT"],
        EventKind.arrived,
        "AKTAU",
        NOW - timedelta(hours=30),
        hold_reason="Погодный запрет на швартовку: Актау — критический ветер",
        hold_code="weather_ban",
        hold_node="AKTAU",
        queue=QueueInput("AKTAU", 4, 8.0, 48.0, "weather_ban"),
    )
    hold = project_shipment(plan, NOW)
    assert hold.state == ShipmentState.waiting and hold.delay_hours >= 18
    assert hold.queue is not None
    assert hold.queue.p50_hours == 60.0
    assert hold.queue.basis_code == "weather_ban"


def test_mock_0501_rides_shahdag_with_ais() -> None:
    """0501 на AIS-пароме: позиция — с парома, плечо Алят → Актау, задержка видна."""
    ts = east_departure(NOW) + timedelta(hours=5)
    state = next(f for f in list_ferry_states(ts) if f.spec.name == EAST_FERRY)
    assert state.sailing and not state.westbound  # отход груза = восточный рейс «Shahdag»
    s = project_shipment(east_plan(ts), ts, {EAST_FERRY: (state.lat, state.lon)})
    assert s.state == ShipmentState.in_transit
    assert s.position.source == PositionSource.ais and s.position.on_vessel == EAST_FERRY
    assert (s.position.lat, s.position.lon) == (state.lat, state.lon)
    assert (s.position.from_code, s.position.to_code, s.position.mode) == (
        "BAKU_ALAT",
        "AKTAU",
        "sea",
    )
    assert s.last_event_note_code == "loaded_on_ferry" and s.delay_hours >= 10


@pytest.mark.parametrize(
    ("before_h", "code", "ferry_at_alat"),
    [(4, "ferry_loading_wait", True), (12, "ferry_return_wait", False)],
)
def test_mock_0501_waits_for_shahdag_in_alat(before_h: int, code: str, ferry_at_alat: bool) -> None:
    ts = east_departure(NOW + timedelta(hours=60)) - timedelta(hours=before_h)
    state = next(f for f in list_ferry_states(ts) if f.spec.name == EAST_FERRY)
    assert (not state.sailing and not state.westbound) == ferry_at_alat
    s = project_shipment(east_plan(ts), ts)
    assert s.state == ShipmentState.waiting and s.position.from_code == "BAKU_ALAT"
    assert s.hold_code == code and s.hold_vessel == EAST_FERRY
    assert s.delay_hours >= 10


async def test_mock_0501_never_jumps_back() -> None:
    """Цикл 0501 — только вперёд; назад в Алят — лишь перезапуск на плече Бейнеу → Костанай.

    «Доставлен» в публичном демо не бывает: иначе фильтр «с задержкой» в e2e пустеет.
    """
    source = MockShipmentSource(lambda: NOW)
    prev: tuple[int, ShipmentState] | None = None
    restarts = 0
    for minutes in range(0, (3 * 112 + 1) * 60, 30):  # три цикла груза, шаг 30 мин
        ts = NOW + timedelta(minutes=minutes)
        plan = next(p for p in await source.list_plans(ts) if p.ref == "MC-26-0501")
        s = project_shipment(plan, ts)
        idx = ROUTE_KOSTANAY.index(s.position.from_code or "")
        assert s.state != ShipmentState.delivered, ts
        assert s.delay_hours >= 10, ts  # фильтр «с задержкой» в e2e
        if prev is not None and idx < prev[0]:
            assert prev == (ROUTE_KOSTANAY.index("BEINEU"), ShipmentState.in_transit), ts
            assert idx == ROUTE_KOSTANAY.index("BAKU_ALAT"), ts
            restarts += 1
        prev = (idx, s.state)
    assert restarts == 3


# --- санкции: пакинг-листы демо-грузов -------------------------------------------

SANCTIONS_EXPECTED = {
    "MC-26-0431": "flagged",  # сталь RU среди автозапчастей
    "MC-26-0501": "clear",  # автокомплекты Škoda в Казахстан
}


async def test_mock_sanctions_statuses(mock_service: MapSnapshotService) -> None:
    snap = await mock_service.snapshot()
    statuses = {s.ref: s.sanctions.status for s in snap.shipments if s.sanctions}
    assert len(statuses) == len(snap.shipments) == 2
    assert statuses == SANCTIONS_EXPECTED


def _review_plan(lines: tuple[PackingLine, ...], consignee: str, route: list[str]) -> Shipment:
    """План с пакинг-листом вне демо: статус «проверить вручную» в публичном демо не показан."""
    plan = build_plan(
        "T-R", "c", "x", route, EventKind.departed, route[2], NOW - timedelta(hours=1)
    )
    packing = PackingList(
        received_at=NOW - timedelta(days=4),
        lines=lines,
        consignee_country=consignee,
        destination_country=consignee,
    )
    return project_shipment(dataclasses.replace(plan, packing_list=packing), NOW)


# бывшие демо-грузы: процессоры из CHPL в Венгрию; разъёмы из CHPL в Казахстан
PROCESSORS = (
    PackingLine(1, "8542310001", "Микросхемы-процессоры", "Processor integrated circuits", "CN"),
    PackingLine(2, "8471300000", "Ноутбуки", "Laptops", "CN"),
    PackingLine(3, "8517130000", "Смартфоны", "Smartphones", "CN"),
)
CONNECTORS = (
    PackingLine(1, "8536699008", "Разъёмы электрические", "Electrical connectors", "DE", 4000, 380),
    PackingLine(2, "8544429009", "Жгуты проводов", "Wiring harnesses", "CZ", 300, 2900),
    PackingLine(3, "8512200009", "Фары", "Headlamps", "CZ", 120, 320),
)


def test_sanctions_review_cases_outside_demo() -> None:
    west = _review_plan(PROCESSORS, "HU", ROUTE_KURYK)
    assert west.sanctions is not None and west.sanctions.status == "review"
    assert [m.line_no for m in west.sanctions.matches] == [1]  # процессоры CHPL
    east = _review_plan(CONNECTORS, "KZ", ROUTE_KOSTANAY)
    assert east.sanctions is not None and east.sanctions.status == "review"
    assert [(x.line_no, x.list_id, x.reason_code) for x in east.sanctions.matches] == [
        (1, "chpl", "code_only")
    ]


async def test_mock_packing_codes_exist_in_lists(mock_service: MapSnapshotService) -> None:
    from app.services.sanctions import default_lists

    known = {(e.list_id, e.code) for e in default_lists().entries}
    snap = await mock_service.snapshot()
    matches = [m for s in snap.shipments if s.sanctions for m in s.sanctions.matches]
    assert matches  # демо показывает совпадения, а не только «чисто»
    assert all((m.list_id, m.list_code) in known for m in matches)


async def test_api_shipment_sanctions_without_packing_list(
    mock_service: MapSnapshotService,
) -> None:
    from app.integrations.mock.packing import DEMO_PACKING

    app = create_app(settings=_settings(), map_service=mock_service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/api/v1/shipments/MC-26-0431")).json()
    sanctions = body["sanctions"]
    assert sanctions["status"] == "flagged"
    first = sanctions["matches"][0]
    assert (
        first["strong"]
        and first["reason_code"] == "origin_ru"
        and first["list_id"] == "eu_833_2014"
    )
    assert "packing_list" not in body and "lines" not in sanctions
    assert len({m["line_no"] for m in sanctions["matches"]}) < len(DEMO_PACKING["MC-26-0431"].lines)


async def test_api_exposes_only_status_driving_lines(mock_service: MapSnapshotService) -> None:
    """Наружу — только позиции, из-за которых статус: справочные совпадения не раскрывают лист."""
    snap = await mock_service.snapshot()
    by_ref = {s.ref: s.sanctions for s in snap.shipments if s.sanctions}
    review = _review_plan(PROCESSORS, "HU", ROUTE_KURYK).sanctions
    assert review is not None
    by_ref["review"] = review
    assert [m.line_no for m in by_ref["review"].matches] == [1]  # процессоры CHPL
    assert [m.line_no for m in by_ref["MC-26-0431"].matches] == [3]  # сталь RU
    for ref, check in by_ref.items():
        if check.status == "clear":
            assert check.matches == [], ref
        assert all(
            m.strong or m.reason_code != "code_only" or m.measure == "export_ban"
            for m in check.matches
        ), ref


async def test_mock_eastbound_shipment(mock_service: MapSnapshotService) -> None:
    """Европа → Казахстан: 0501 на линии Алят — Актау, «чисто»."""
    snap = await mock_service.snapshot()
    east = {s.ref: s for s in snap.shipments}["MC-26-0501"]
    assert east.origin_code == "MLADA_BOLESLAV" and east.destination_code == "KOSTANAY"
    assert east.position.from_code in ROUTE_KOSTANAY[ROUTE_KOSTANAY.index("BAKU_ALAT") :]
    assert east.sanctions and east.sanctions.status == "clear" and east.sanctions.matches == []


async def test_mock_eastbound_cargo_details(mock_service: MapSnapshotService) -> None:
    """Блок «Груз» у восточного демо-груза: контейнер, места, вес, опасный груз, главные позиции."""
    app = create_app(settings=_settings(), map_service=mock_service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/api/v1/shipments/MC-26-0501")).json()
    cargo = body["cargo_details"]
    assert cargo["container_no"] == "DEMU5010012"
    assert cargo["container_type"] == "40' HC" and cargo["packages"] == 14
    assert [(g["un_number"], g["hazard_class"]) for g in cargo["dangerous"]] == [("2800", "8")]
    assert len(cargo["top_items"]) == 5 and cargo["more_items"] == 4
    assert cargo["top_items"][0]["net_kg"] >= cargo["top_items"][-1]["net_kg"]
    assert "value" not in str(cargo).lower() and "price" not in str(cargo).lower()
    snap = await mock_service.snapshot()
    with_cargo = {s.ref for s in snap.shipments if s.cargo_details}
    assert with_cargo == {"MC-26-0501", "MC-26-0431"}  # 0431 — по пакинг-листу
    # ни листа, ни сведений — блока «Груз» нет
    bare = build_plan("T-B", "c", "x", ROUTE_KURYK, EventKind.departed, "XIAN", NOW)
    assert project_shipment(bare, NOW).cargo_details is None
