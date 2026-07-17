"""Ручной слой: приём, валидация и модерация данных доверенных источников (§7.4).

Payload каждого типа проверяется pydantic-моделью со строгой схемой
(extra="forbid"): мусор от источника не попадёт в БД и в канал.
Публикация: AUTO_PUBLISH_REPORTS=false — сводки копятся и публикуются
админом через /approve; true — публикуются сразу при приёме.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ManualReport, Port, ReportType, TrustedSource
from app.db.repositories.reports import ReportsRepository
from app.services.formatting import format_manual_report
from app.services.sinks import MessageSink

logger = structlog.get_logger(__name__)


class ManualReportError(Exception):
    """Ошибка ручного слоя; текст пригоден для показа пользователю."""


class NotTrustedError(ManualReportError):
    pass


class InvalidPayloadError(ManualReportError):
    pass


class ReportNotFoundError(ManualReportError):
    pass


# --- Схемы payload по типам ---------------------------------------------------


class QueuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vessels_waiting: int = Field(ge=0, le=500)
    ferry_expected: date | None = None


class RatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate_usd: float = Field(gt=0, le=1_000_000)


class BorderDelayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    border: str = Field(min_length=2, max_length=128)
    delay_hours: float = Field(ge=0, le=24 * 30)


class NotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


_PAYLOAD_MODELS: dict[ReportType, type[BaseModel]] = {
    ReportType.queue: QueuePayload,
    ReportType.rate: RatePayload,
    ReportType.border_delay: BorderDelayPayload,
    ReportType.note: NotePayload,
}


def validate_payload(report_type: ReportType, payload: dict[str, Any]) -> dict[str, Any]:
    """Проверяет payload по схеме типа; возвращает нормализованный dict (JSON-типы)."""
    model = _PAYLOAD_MODELS[report_type]
    try:
        validated = model.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "payload"
        raise InvalidPayloadError(f"{field}: {first['msg']}") from exc
    return validated.model_dump(mode="json", exclude_none=True)


@dataclass(frozen=True, slots=True)
class SubmitResult:
    report_id: int
    published: bool


class ManualReportsService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sink: MessageSink | None = None,
        auto_publish: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._sink = sink
        self._auto_publish = auto_publish

    async def is_trusted(self, tg_user_id: int) -> bool:
        async with self._session_factory() as session:
            source = await ReportsRepository(session).get_trusted(tg_user_id)
            return source is not None and source.is_active

    async def list_ports(self) -> list[Port]:
        async with self._session_factory() as session:
            return list(await ReportsRepository(session).list_ports())

    async def submit(
        self,
        tg_user_id: int,
        report_type: ReportType,
        payload: dict[str, Any],
        note: str | None = None,
        port_id: int | None = None,
    ) -> SubmitResult:
        clean_payload = validate_payload(report_type, payload)
        async with self._session_factory() as session:
            repo = ReportsRepository(session)
            source = await repo.get_trusted(tg_user_id)
            if source is None or not source.is_active:
                raise NotTrustedError("Источник не в whitelist или деактивирован")
            report = await repo.add_report(
                source_id=source.id,
                report_type=report_type,
                payload=clean_payload,
                note=note,
                ts=datetime.now(UTC),
                port_id=port_id,
            )
            published = False
            if self._auto_publish:
                port = await repo.get_port(port_id) if port_id is not None else None
                published = await self._try_publish(report, port)
                report.is_published = published
            await session.commit()
            logger.info(
                "manual_report_submitted",
                report_id=report.id,
                type=report_type.value,
                source=source.name,
                published=published,
            )
            return SubmitResult(report_id=report.id, published=published)

    async def approve(self, report_id: int) -> ManualReport:
        """Публикует сводку в канал. Ошибка публикации не помечает её опубликованной."""
        async with self._session_factory() as session:
            repo = ReportsRepository(session)
            report = await repo.get_report(report_id)
            if report is None:
                raise ReportNotFoundError(f"Сводка #{report_id} не найдена")
            if report.is_published:
                raise ManualReportError(f"Сводка #{report_id} уже опубликована")
            if self._sink is not None:
                port_name = report.port.name if report.port is not None else None
                await self._sink.publish(self._format(report, port_name))
            report.is_published = True
            await session.commit()
            logger.info("manual_report_approved", report_id=report_id)
            return report

    async def reject(self, report_id: int) -> None:
        async with self._session_factory() as session:
            repo = ReportsRepository(session)
            report = await repo.get_report(report_id)
            if report is None:
                raise ReportNotFoundError(f"Сводка #{report_id} не найдена")
            await repo.delete_report(report)
            await session.commit()
            logger.info("manual_report_rejected", report_id=report_id)

    async def list_pending(self) -> list[ManualReport]:
        async with self._session_factory() as session:
            return list(await ReportsRepository(session).list_pending())

    async def add_trusted_source(self, tg_user_id: int, name: str, role: str) -> TrustedSource:
        async with self._session_factory() as session:
            source = await ReportsRepository(session).upsert_trusted(tg_user_id, name, role)
            await session.commit()
            logger.info("trusted_source_upserted", tg_user_id=tg_user_id, role=role)
            return source

    async def _try_publish(self, report: ManualReport, port: Port | None) -> bool:
        if self._sink is None:
            return False
        try:
            await self._sink.publish(self._format(report, port.name if port else None))
            return True
        except Exception as exc:  # noqa: BLE001 — сводка останется в pending
            logger.error("manual_report_publish_failed", report_id=report.id, error=str(exc))
            return False

    @staticmethod
    def _format(report: ManualReport, port_name: str | None) -> str:
        return format_manual_report(
            report.report_type.value, report.payload, report.note, report.ts, port_name
        )
