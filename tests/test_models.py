"""Smoke-тест моделей: схема создаётся на SQLite, базовые операции работают."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AlertLevel,
    CheckpointEventKind,
    CorridorLeg,
    Membership,
    Organization,
    OrgKind,
    Port,
    Role,
    ShipmentEventRow,
    ShipmentRow,
    User,
    WeatherAlert,
)


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


async def test_account_tables_roundtrip(session: AsyncSession) -> None:
    org = Organization(name="Forwarder LLC", kind=OrgKind.forwarder)
    user = User(email="agent@example.com", name="Агент")
    session.add_all([org, user])
    await session.flush()

    session.add(Membership(user_id=user.id, org_id=org.id, role=Role.agent, node_codes=["AKTAU"]))
    shipment = ShipmentRow(
        ref="MC-26-0001", org_id=org.id, route=["KOPER", "AKTAU"], cargo="Запчасти"
    )
    session.add(shipment)
    await session.flush()
    session.add(
        ShipmentEventRow(
            shipment_id=shipment.id,
            kind=CheckpointEventKind.arrived,
            node_code="AKTAU",
            occurred_at=datetime.now(UTC),
        )
    )
    await session.commit()

    membership = (await session.execute(select(Membership))).scalar_one()
    assert membership.role is Role.agent
    assert membership.node_codes == ["AKTAU"]
    stored = (await session.execute(select(ShipmentRow))).scalar_one()
    assert stored.route == ["KOPER", "AKTAU"]
    assert stored.created_at is not None
    event = (await session.execute(select(ShipmentEventRow))).scalar_one()
    assert event.kind is CheckpointEventKind.arrived
    assert event.source == "manual"

    session.add(Membership(user_id=user.id, org_id=org.id, role=Role.viewer, node_codes=[]))
    with pytest.raises(IntegrityError):
        await session.commit()
