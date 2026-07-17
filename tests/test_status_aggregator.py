"""Тесты агрегатора статуса и форматтера сводки (§7.5)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AlertLevel,
    CorridorLeg,
    ManualReport,
    Port,
    PositionSource,
    ReportType,
    TrustedSource,
    Vessel,
    VesselPosition,
    WeatherAlert,
    WeatherSnapshot,
)
from app.services.formatting import format_corridor_status, format_port_detail
from app.services.status_aggregator import StatusAggregatorService

NOW = datetime.now(UTC)


@pytest.fixture
async def seeded(session: AsyncSession) -> dict:
    aktau = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
    )
    poti = Port(
        code="POTI",
        name="Поти",
        country="Грузия",
        leg=CorridorLeg.black_sea,
        lat=42.15,
        lon=41.65,
    )
    gul = Vessel(mmsi=423000001, name="Professor Gul", operator="ASCO")
    barda = Vessel(mmsi=None, name="Barda", operator="ASCO")
    source = TrustedSource(tg_user_id=1001, name="Агент", role="port_agent")
    session.add_all([aktau, poti, gul, barda, source])
    await session.flush()

    session.add_all(
        [
            # два снимка — агрегатор должен взять свежий
            WeatherSnapshot(
                port_id=aktau.id,
                wind_speed=5.0,
                wind_gust=7.0,
                wind_dir=180.0,
                ts=NOW - timedelta(hours=2),
            ),
            WeatherSnapshot(
                port_id=aktau.id,
                wind_speed=15.0,
                wind_gust=19.0,
                wind_dir=200.0,
                ts=NOW,
            ),
            WeatherAlert(
                port_id=aktau.id,
                level=AlertLevel.warning,
                message="Ветер 15 м/с, порывы до 19 м/с",
                opened_at=NOW,
                is_active=True,
            ),
            # закрытый алерт не должен попадать в сводку
            WeatherAlert(
                port_id=poti.id,
                level=AlertLevel.critical,
                message="старое",
                opened_at=NOW - timedelta(days=2),
                closed_at=NOW - timedelta(days=1),
                is_active=False,
            ),
            # свежая позиция парома
            VesselPosition(
                vessel_id=gul.id,
                lat=42.0,
                lon=50.0,
                sog=10.0,
                ts=NOW - timedelta(hours=1),
                source=PositionSource.aisstream,
            ),
            ManualReport(
                source_id=source.id,
                port_id=aktau.id,
                report_type=ReportType.queue,
                payload={"vessels_waiting": 4},
                ts=NOW - timedelta(hours=3),
                is_published=True,
            ),
            # неопубликованная — не должна попасть
            ManualReport(
                source_id=source.id,
                port_id=aktau.id,
                report_type=ReportType.note,
                payload={},
                note="черновик",
                ts=NOW,
                is_published=False,
            ),
            # старая опубликованная — за окном 48 ч
            ManualReport(
                source_id=source.id,
                port_id=poti.id,
                report_type=ReportType.rate,
                payload={"rate_usd": 900},
                ts=NOW - timedelta(days=5),
                is_published=True,
            ),
        ]
    )
    await session.commit()
    return {"aktau": aktau, "poti": poti}


@pytest.fixture
def service(session_factory: async_sessionmaker[AsyncSession]) -> StatusAggregatorService:
    return StatusAggregatorService(session_factory, vessel_stale_after=timedelta(hours=6))


async def test_corridor_status_ports(service: StatusAggregatorService, seeded: dict) -> None:
    status = await service.get_corridor_status()

    aktau = next(port for port in status.ports if port.code == "AKTAU")
    assert aktau.alert_level is AlertLevel.warning
    assert aktau.wind_speed == 15.0  # свежий снимок, не старый
    assert aktau.alert_message and "15 м/с" in aktau.alert_message

    poti = next(port for port in status.ports if port.code == "POTI")
    assert poti.alert_level is None  # закрытый алерт не считается
    assert poti.wind_speed is None  # снимков нет


async def test_corridor_status_vessels_honest_no_data(
    service: StatusAggregatorService, seeded: dict
) -> None:
    status = await service.get_corridor_status()
    by_name = {vessel.name: vessel for vessel in status.vessels}

    assert by_name["Professor Gul"].has_recent_data is True
    assert by_name["Professor Gul"].sog == 10.0
    assert by_name["Barda"].has_recent_data is False  # позиций нет — «нет данных»
    assert by_name["Barda"].ts is None


async def test_stale_position_is_no_data(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    seeded: dict,
) -> None:
    service = StatusAggregatorService(session_factory, vessel_stale_after=timedelta(minutes=30))
    status = await service.get_corridor_status()
    gul = next(vessel for vessel in status.vessels if vessel.name == "Professor Gul")
    assert gul.has_recent_data is False  # позиция часовой давности старше порога 30 мин


async def test_recent_reports_only_published_and_fresh(
    service: StatusAggregatorService, seeded: dict
) -> None:
    status = await service.get_corridor_status()
    assert len(status.recent_reports) == 1
    report = status.recent_reports[0]
    assert report.report_type == "queue"
    assert report.port_name == "Актау"


async def test_port_lookup_by_code_and_name(service: StatusAggregatorService, seeded: dict) -> None:
    by_code = await service.get_port_status("aktau")
    assert by_code is not None and by_code.code == "AKTAU"

    by_name = await service.get_port_status("Пот")
    assert by_name is not None and by_name.code == "POTI"

    assert await service.get_port_status("нарния") is None


async def test_format_corridor_status(service: StatusAggregatorService, seeded: dict) -> None:
    text = format_corridor_status(await service.get_corridor_status())

    assert "Каспий" in text and "Чёрное море" in text
    assert "⚠️ Актау" in text  # алерт с маркером уровня
    assert "⚪️ Поти — нет данных о погоде" in text
    assert "Professor Gul — в эфире" in text
    assert "нет данных: 1 судов" in text
    assert "vessels_waiting: 4" in text
    assert "Обновлено:" in text


async def test_format_port_detail(service: StatusAggregatorService, seeded: dict) -> None:
    port = await service.get_port_status("AKTAU")
    assert port is not None
    text = format_port_detail(port)
    assert text.startswith("<b>Актау</b> (Казахстан) · Каспий")
    assert "риск остановки операций" in text
    assert "Ветер 15 м/с" in text
