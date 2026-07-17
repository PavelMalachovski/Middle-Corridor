"""Тесты ручного слоя: whitelist, валидация payload, модерация (§7.4)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CorridorLeg, ManualReport, Port, ReportType, TrustedSource
from app.services.manual_reports import (
    InvalidPayloadError,
    ManualReportError,
    ManualReportsService,
    NotTrustedError,
    ReportNotFoundError,
    validate_payload,
)

TRUSTED_ID = 1001
INACTIVE_ID = 1002
UNKNOWN_ID = 9999


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.error: Exception | None = None

    async def publish(self, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(text)


@pytest.fixture
async def seeded(session: AsyncSession) -> Port:
    port = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
    )
    session.add_all(
        [
            port,
            TrustedSource(tg_user_id=TRUSTED_ID, name="Агент", role="port_agent"),
            TrustedSource(tg_user_id=INACTIVE_ID, name="Бывший", role="operator", is_active=False),
        ]
    )
    await session.commit()
    return port


@pytest.fixture
def sink() -> FakeSink:
    return FakeSink()


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession], sink: FakeSink
) -> ManualReportsService:
    return ManualReportsService(session_factory, sink, auto_publish=False)


# --- Валидация payload ---------------------------------------------------------


def test_queue_payload_valid() -> None:
    clean = validate_payload(
        ReportType.queue, {"vessels_waiting": 4, "ferry_expected": "2026-07-18"}
    )
    assert clean == {"vessels_waiting": 4, "ferry_expected": "2026-07-18"}


def test_queue_payload_negative_vessels_rejected() -> None:
    with pytest.raises(InvalidPayloadError, match="vessels_waiting"):
        validate_payload(ReportType.queue, {"vessels_waiting": -1})


def test_queue_payload_bad_date_rejected() -> None:
    with pytest.raises(InvalidPayloadError, match="ferry_expected"):
        validate_payload(ReportType.queue, {"vessels_waiting": 1, "ferry_expected": "завтра"})


def test_rate_payload_zero_rejected() -> None:
    with pytest.raises(InvalidPayloadError, match="rate_usd"):
        validate_payload(ReportType.rate, {"rate_usd": 0})


def test_unknown_keys_rejected() -> None:
    with pytest.raises(InvalidPayloadError):
        validate_payload(ReportType.note, {"surprise": 1})


def test_border_delay_requires_border_name() -> None:
    with pytest.raises(InvalidPayloadError, match="border"):
        validate_payload(ReportType.border_delay, {"delay_hours": 5})


# --- Whitelist -----------------------------------------------------------------


async def test_is_trusted(service: ManualReportsService, seeded: Port) -> None:
    assert await service.is_trusted(TRUSTED_ID) is True
    assert await service.is_trusted(INACTIVE_ID) is False
    assert await service.is_trusted(UNKNOWN_ID) is False


async def test_submit_from_unknown_user_rejected(
    service: ManualReportsService, seeded: Port
) -> None:
    with pytest.raises(NotTrustedError):
        await service.submit(UNKNOWN_ID, ReportType.note, {}, note="привет")


async def test_submit_from_inactive_source_rejected(
    service: ManualReportsService, seeded: Port
) -> None:
    with pytest.raises(NotTrustedError):
        await service.submit(INACTIVE_ID, ReportType.note, {}, note="я вернулся")


# --- Приём и модерация -----------------------------------------------------------


async def test_submit_goes_to_moderation_by_default(
    service: ManualReportsService,
    sink: FakeSink,
    session: AsyncSession,
    seeded: Port,
) -> None:
    result = await service.submit(
        TRUSTED_ID,
        ReportType.queue,
        {"vessels_waiting": 4, "ferry_expected": "2026-07-18"},
        port_id=seeded.id,
    )
    assert result.published is False
    assert sink.messages == []

    report = (await session.execute(select(ManualReport))).scalar_one()
    assert report.is_published is False
    assert report.payload["vessels_waiting"] == 4


async def test_auto_publish_mode(
    session_factory: async_sessionmaker[AsyncSession],
    sink: FakeSink,
    session: AsyncSession,
    seeded: Port,
) -> None:
    service = ManualReportsService(session_factory, sink, auto_publish=True)
    result = await service.submit(
        TRUSTED_ID, ReportType.rate, {"rate_usd": 1500}, port_id=seeded.id
    )
    assert result.published is True
    assert len(sink.messages) == 1
    assert "Ставка" in sink.messages[0] and "Актау" in sink.messages[0]


async def test_auto_publish_failure_keeps_report_pending(
    session_factory: async_sessionmaker[AsyncSession],
    sink: FakeSink,
    session: AsyncSession,
    seeded: Port,
) -> None:
    sink.error = RuntimeError("telegram down")
    service = ManualReportsService(session_factory, sink, auto_publish=True)
    result = await service.submit(TRUSTED_ID, ReportType.rate, {"rate_usd": 900})
    assert result.published is False

    report = (await session.execute(select(ManualReport))).scalar_one()
    assert report.is_published is False  # осталась в pending


async def test_approve_publishes_and_marks(
    service: ManualReportsService,
    sink: FakeSink,
    session: AsyncSession,
    seeded: Port,
) -> None:
    result = await service.submit(
        TRUSTED_ID, ReportType.queue, {"vessels_waiting": 2}, port_id=seeded.id
    )
    approved = await service.approve(result.report_id)
    assert approved.is_published is True
    assert len(sink.messages) == 1
    assert "Очередь — Актау" in sink.messages[0]

    with pytest.raises(ManualReportError, match="уже опубликована"):
        await service.approve(result.report_id)


async def test_approve_unknown_id(service: ManualReportsService, seeded: Port) -> None:
    with pytest.raises(ReportNotFoundError):
        await service.approve(12345)


async def test_reject_deletes_report(
    service: ManualReportsService, session: AsyncSession, seeded: Port
) -> None:
    result = await service.submit(TRUSTED_ID, ReportType.note, {}, note="шум")
    await service.reject(result.report_id)

    count = (await session.execute(select(func.count(ManualReport.id)))).scalar_one()
    assert count == 0

    with pytest.raises(ReportNotFoundError):
        await service.reject(result.report_id)


async def test_pending_lists_only_unpublished(
    service: ManualReportsService, sink: FakeSink, seeded: Port
) -> None:
    first = await service.submit(TRUSTED_ID, ReportType.note, {}, note="раз")
    await service.submit(TRUSTED_ID, ReportType.note, {}, note="два")
    await service.approve(first.report_id)

    pending = await service.list_pending()
    assert len(pending) == 1
    assert pending[0].note == "два"
    assert pending[0].source.name == "Агент"  # связи загружены


async def test_add_trusted_source_upsert_reactivates(
    service: ManualReportsService, seeded: Port
) -> None:
    await service.add_trusted_source(INACTIVE_ID, "Вернулся", "forwarder")
    assert await service.is_trusted(INACTIVE_ID) is True

    with pytest.raises(ManualReportError):
        # payload всё ещё валидируется даже для вернувшихся
        await service.submit(INACTIVE_ID, ReportType.rate, {"rate_usd": -5})
