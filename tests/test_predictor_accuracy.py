"""Журнал остановок, точность алертов и подбор порогов на БД (SQLite)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from aiogram.filters import CommandObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.bot.handlers.closures import (
    cmd_accuracy,
    cmd_calibrate,
    cmd_closed,
    cmd_closure,
    cmd_reopened,
    parse_cause_note,
    parse_utc,
)
from app.config import Settings
from app.db.models import (
    AlertLevel,
    ClosureCause,
    CorridorLeg,
    Port,
    PortClosure,
    WeatherAlert,
    WeatherSnapshot,
)
from app.integrations.weather.base import WindObservation
from app.integrations.weather.open_meteo import OPEN_METEO_ARCHIVE_URL, OpenMeteoProvider
from app.services.formatting import format_calibration
from app.services.predictor_accuracy import ClosureError, PredictorAccuracyService
from app.services.weather_predictor import WindThresholds

NOW = datetime(2025, 3, 1, 12, tzinfo=UTC)
THRESHOLDS = WindThresholds(
    watch_wind=10, warning_wind=13.8, warning_gust=15, critical_wind=17, critical_gust=21
)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def ports(session: AsyncSession) -> list[Port]:
    ports = [
        Port(
            code="AKTAU",
            name="Актау",
            country="Казахстан",
            leg=CorridorLeg.caspian,
            lat=43.63,
            lon=51.25,
            is_weather_tracked=True,
        ),
        Port(
            code="BAKU",
            name="Баку (Алят)",
            country="Азербайджан",
            leg=CorridorLeg.caspian,
            lat=40.0,
            lon=49.4,
            is_weather_tracked=True,
        ),
    ]
    session.add_all(ports)
    await session.commit()
    return ports


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession], ports: list[Port], clock: Clock
) -> PredictorAccuracyService:
    return PredictorAccuracyService(session_factory, THRESHOLDS, clock=clock)


async def test_close_and_reopen_by_name(
    service: PredictorAccuracyService, clock: Clock, session: AsyncSession
) -> None:
    info = await service.close_port("актау", note="шторм", reported_by=42)
    assert info.port_code == "AKTAU" and info.ended_at is None
    with pytest.raises(ClosureError, match="уже открыта"):
        await service.close_port("AKTAU")

    clock.now = NOW + timedelta(hours=30)
    reopened = await service.reopen_port("aktau")
    assert reopened.duration == timedelta(hours=30)
    with pytest.raises(ClosureError, match="открытой остановки нет"):
        await service.reopen_port("aktau")

    row = (await session.execute(select(PortClosure))).scalar_one()
    assert (row.cause, row.note, row.reported_by) == (ClosureCause.wind, "шторм", 42)


async def test_unknown_port(service: PredictorAccuracyService) -> None:
    with pytest.raises(ClosureError, match="не найден"):
        await service.close_port("атлантида")


async def test_historical_closure_validation(service: PredictorAccuracyService) -> None:
    start = datetime(2024, 11, 12, 6, tzinfo=UTC)
    info = await service.add_closure("aktau", start, start + timedelta(hours=36))
    assert info.duration == timedelta(hours=36)
    with pytest.raises(ClosureError, match="уже записана"):
        await service.add_closure("aktau", start + timedelta(hours=1), start + timedelta(hours=2))
    with pytest.raises(ClosureError, match="позже начала"):
        await service.add_closure("baku", start, start)
    with pytest.raises(ClosureError, match="ещё не закончилась"):
        await service.add_closure("baku", NOW - timedelta(hours=1), NOW + timedelta(hours=1))


async def test_accuracy_per_port(
    service: PredictorAccuracyService, session: AsyncSession, ports: list[Port]
) -> None:
    aktau, baku = ports
    t = NOW - timedelta(days=10)
    session.add_all(
        [
            # Актау: алерт за 8 ч до остановки — попадание; эскалация — один эпизод
            WeatherAlert(
                port_id=aktau.id,
                level=AlertLevel.warning,
                message="",
                opened_at=t,
                closed_at=t + timedelta(hours=6),
                is_active=False,
            ),
            WeatherAlert(
                port_id=aktau.id,
                level=AlertLevel.critical,
                message="",
                opened_at=t + timedelta(hours=6),
                closed_at=t + timedelta(hours=20),
                is_active=False,
            ),
            PortClosure(
                port_id=aktau.id,
                started_at=t + timedelta(hours=8),
                ended_at=t + timedelta(hours=18),
                cause=ClosureCause.wind,
            ),
            # туман в калибровку ветра не идёт
            PortClosure(
                port_id=aktau.id,
                started_at=t + timedelta(days=3),
                ended_at=t + timedelta(days=3, hours=5),
                cause=ClosureCause.other,
            ),
            # Баку: watch — не публикуемый алерт, остановка без предупреждения — промах
            WeatherAlert(
                port_id=baku.id,
                level=AlertLevel.watch,
                message="",
                opened_at=t,
                closed_at=t + timedelta(hours=3),
                is_active=False,
            ),
            PortClosure(
                port_id=baku.id,
                started_at=t + timedelta(hours=2),
                ended_at=t + timedelta(hours=5),
                cause=ClosureCause.wind,
            ),
        ]
    )
    await session.commit()

    by_code = {p.code: p for p in await service.accuracy(days=30)}
    akt = by_code["AKTAU"].score
    assert (akt.closures, akt.hits, akt.episodes, akt.false_alarms) == (1, 1, 1, 0)
    assert akt.median_lead_h == pytest.approx(8.0)
    bak = by_code["BAKU"].score
    assert (bak.closures, bak.hits, bak.episodes) == (1, 0, 0)


async def test_calibrate_from_snapshots(
    service: PredictorAccuracyService, session: AsyncSession, ports: list[Port]
) -> None:
    aktau = ports[0]
    start = NOW - timedelta(days=20)
    winds = [8, 9, 12, 14, 16, 18, 20, 17, 15, 11, 9, 7] * 4
    closure_start = None
    for i, wind in enumerate(winds):
        ts = start + timedelta(hours=i)
        session.add(
            WeatherSnapshot(
                port_id=aktau.id, wind_speed=wind, wind_gust=wind + 5, wind_dir=270, ts=ts
            )
        )
        if wind >= 16 and closure_start is None:
            closure_start = ts
        if wind < 16 and closure_start is not None:
            session.add(
                PortClosure(
                    port_id=aktau.id,
                    started_at=closure_start,
                    ended_at=ts - timedelta(hours=1),
                    cause=ClosureCause.wind,
                )
            )
            closure_start = None
    await session.commit()

    report = await service.calibrate("aktau", days=60)
    assert report.code == "AKTAU"
    assert report.result.closures == 4
    assert report.result.samples == len(winds)
    best = report.result.best_critical
    assert best is not None and best.misses == 0 and best.false_alarms == 0

    text = format_calibration(report, 60)
    assert "Подсказка по фактам" in text
    assert "critical (лучший CSI): ветер ≥" in text and "CSI 100%" in text
    assert "Пороги сами не меняются" in text


async def test_calibrate_without_facts_gives_no_suggestion(
    service: PredictorAccuracyService,
) -> None:
    report = await service.calibrate("baku")
    assert not report.result.enough_data


class FakeHistory:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    async def get_wind_history(
        self, lat: float, lon: float, start: date, end: date
    ) -> list[WindObservation]:
        self.calls.append((start, end))
        out = []
        day = start
        while day <= end:
            ts = datetime(day.year, day.month, day.day, tzinfo=UTC)
            out.append(WindObservation(wind_speed=10, wind_gust=14, wind_dir=90, ts=ts))
            day += timedelta(days=1)
        return out


async def test_backfill_chunks_and_skips_known_hours(
    service: PredictorAccuracyService, session: AsyncSession
) -> None:
    history = FakeHistory()
    added = await service.backfill(history, date(2024, 1, 1), date(2024, 12, 31), "aktau")
    assert added == {"AKTAU": 366}
    assert len(history.calls) == 4  # кварталы по 92 дня
    assert history.calls[0] == (date(2024, 1, 1), date(2024, 4, 1))

    again = await service.backfill(history, date(2024, 6, 1), date(2024, 6, 30), "aktau")
    assert again == {"AKTAU": 0}
    rows = (await session.execute(select(WeatherSnapshot))).scalars().all()
    assert len(rows) == 366
    assert rows[0].raw == {"source": "open-meteo-archive"}


async def test_open_meteo_archive_request_and_parse() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2024-11-12T00:00", "2024-11-12T01:00", "2024-11-12T02:00"],
                    "wind_speed_10m": [15.2, 17.9, None],
                    "wind_gusts_10m": [21.0, 24.5, None],
                    "wind_direction_10m": [320, 325, None],
                }
            },
        )

    provider = OpenMeteoProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    history = await provider.get_wind_history(43.6, 51.2, date(2024, 11, 12), date(2024, 11, 12))
    await provider.aclose()
    assert str(seen[0].url).startswith(OPEN_METEO_ARCHIVE_URL)
    params = seen[0].url.params
    assert (params["start_date"], params["end_date"]) == ("2024-11-12", "2024-11-12")
    assert params["wind_speed_unit"] == "ms"
    assert [(o.wind_speed, o.wind_gust) for o in history] == [(15.2, 21.0), (17.9, 24.5)]
    assert history[0].ts == datetime(2024, 11, 12, tzinfo=UTC)


# --- бот, API, форматирование -------------------------------------------------------


class FakeMessage:
    """Хендлеры трогают только from_user и answer()."""

    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


class FakeReports:
    def __init__(self, trusted: set[int]) -> None:
        self._trusted = trusted

    async def is_trusted(self, tg_user_id: int) -> bool:
        return tg_user_id in self._trusted


ADMIN, TRUSTED, STRANGER = 1, 2, 3


def cmd(name: str, args: str | None) -> CommandObject:
    return CommandObject(command=name, args=args)


@pytest.fixture
def bot_settings() -> Settings:
    return Settings(_env_file=None, admin_user_ids=[ADMIN])  # type: ignore[call-arg]


def test_parse_cause_note() -> None:
    assert parse_cause_note([]) == (ClosureCause.wind, None)
    assert parse_cause_note(["другое", "туман", "<b>"]) == (ClosureCause.other, "туман <b>")
    assert parse_cause_note(["швартовка", "запрещена"]) == (
        ClosureCause.wind,
        "швартовка запрещена",
    )
    assert parse_utc("2024-11-12T06:00") == datetime(2024, 11, 12, 6, tzinfo=UTC)


async def test_closed_command_permissions_and_escaping(
    service: PredictorAccuracyService, bot_settings: Settings
) -> None:
    reports: Any = FakeReports(trusted={TRUSTED})

    stranger = FakeMessage(STRANGER)
    await cmd_closed(stranger, cmd("closed", "aktau"), bot_settings, reports, service)
    assert "могут админы и доверенные" in stranger.answers[0]

    source = FakeMessage(TRUSTED)
    await cmd_closed(source, cmd("closed", "aktau ветер шторм"), bot_settings, reports, service)
    assert "Актау: остановка записана" in source.answers[0]
    assert "/reopened aktau" in source.answers[0]

    again = FakeMessage(ADMIN)
    await cmd_closed(again, cmd("closed", "aktau"), bot_settings, reports, service)
    assert "уже открыта" in again.answers[0]

    unknown = FakeMessage(ADMIN)
    await cmd_closed(unknown, cmd("closed", "<b>"), bot_settings, reports, service)
    assert "&lt;b&gt;" in unknown.answers[0] and "<b>" not in unknown.answers[0]

    reopen = FakeMessage(TRUSTED)
    await cmd_reopened(reopen, cmd("reopened", "актау"), bot_settings, reports, service)
    assert "снова работает" in reopen.answers[0]


async def test_admin_only_commands(
    service: PredictorAccuracyService, bot_settings: Settings
) -> None:
    stranger = FakeMessage(TRUSTED)
    await cmd_accuracy(stranger, cmd("accuracy", None), bot_settings, service)
    assert stranger.answers == []  # не админ — молчание, как у admin-роутера

    admin = FakeMessage(ADMIN)
    await cmd_closure(
        admin,
        cmd("closure", "aktau 2024-11-12T06:00 2024-11-13T06:00 ветер"),
        bot_settings,
        service,
    )
    assert "24 ч, ветер" in admin.answers[0]
    await cmd_closure(admin, cmd("closure", "aktau вчера сегодня"), bot_settings, service)
    assert "Прошлая остановка" in admin.answers[1]

    await cmd_accuracy(admin, cmd("accuracy", "3650"), bot_settings, service)
    assert "Точность предиктора · 3650 дн." in admin.answers[2]
    assert "<b>Актау</b>: остановок 1, предсказано 0" in admin.answers[2]

    await cmd_calibrate(admin, cmd("calibrate", "aktau 3650"), bot_settings, service)
    assert "Калибровка · Актау" in admin.answers[3]
    assert "Мало фактов" in admin.answers[3]  # одна остановка и ни одного наблюдения ветра
    await cmd_calibrate(admin, cmd("calibrate", "aktau дни"), bot_settings, service)
    assert "Использование: /calibrate" in admin.answers[4]


async def test_accuracy_endpoint(service: PredictorAccuracyService) -> None:
    await service.add_closure(
        "aktau", NOW - timedelta(days=2), NOW - timedelta(days=1), note="шторм"
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings=settings, accuracy_service=service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/accuracy", params={"days": 30})
        assert response.status_code == 200
        body = response.json()
        assert body["days"] == 30
        aktau = next(p for p in body["ports"] if p["code"] == "AKTAU")
        assert (aktau["closures"], aktau["hits"], aktau["pod"]) == (1, 0, 0.0)
        assert (await client.get("/api/v1/accuracy", params={"days": 0})).status_code == 422

    no_db = create_app(settings=settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=no_db), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/accuracy")).status_code == 503
