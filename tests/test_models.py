"""Smoke-тест моделей: схема создаётся на SQLite, базовые операции работают."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertLevel, CorridorLeg, Port, WeatherAlert


async def test_create_port_and_alert(session: AsyncSession) -> None:
    port = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
        is_weather_tracked=True,
    )
    session.add(port)
    await session.flush()

    alert = WeatherAlert(
        port_id=port.id,
        level=AlertLevel.warning,
        message="Ветер 15 м/с",
        opened_at=datetime.now(UTC),
    )
    session.add(alert)
    await session.commit()

    stored = (await session.execute(select(WeatherAlert))).scalar_one()
    assert stored.level is AlertLevel.warning
    assert stored.is_active is True
    assert stored.closed_at is None
