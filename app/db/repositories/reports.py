"""Доступ к данным ручного слоя: trusted_sources и manual_reports."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ManualReport, Port, ReportType, TrustedSource


class ReportsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- trusted sources ---

    async def get_trusted(self, tg_user_id: int) -> TrustedSource | None:
        result = await self._session.execute(
            select(TrustedSource).where(TrustedSource.tg_user_id == tg_user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_trusted(self, tg_user_id: int, name: str, role: str) -> TrustedSource:
        source = await self.get_trusted(tg_user_id)
        if source is None:
            source = TrustedSource(tg_user_id=tg_user_id, name=name, role=role, is_active=True)
            self._session.add(source)
        else:
            source.name = name
            source.role = role
            source.is_active = True
        await self._session.flush()
        return source

    # --- reports ---

    async def add_report(
        self,
        source_id: int,
        report_type: ReportType,
        payload: dict[str, Any],
        note: str | None,
        ts: datetime,
        port_id: int | None,
    ) -> ManualReport:
        report = ManualReport(
            source_id=source_id,
            port_id=port_id,
            report_type=report_type,
            payload=payload,
            note=note,
            ts=ts,
            is_published=False,
        )
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_report(self, report_id: int) -> ManualReport | None:
        result = await self._session.execute(
            select(ManualReport)
            .where(ManualReport.id == report_id)
            .options(selectinload(ManualReport.port), selectinload(ManualReport.source))
        )
        return result.scalar_one_or_none()

    async def list_pending(self) -> Sequence[ManualReport]:
        result = await self._session.execute(
            select(ManualReport)
            .where(ManualReport.is_published.is_(False))
            .options(selectinload(ManualReport.port), selectinload(ManualReport.source))
            .order_by(ManualReport.id)
        )
        return result.scalars().all()

    async def delete_report(self, report: ManualReport) -> None:
        await self._session.delete(report)

    # --- справочники ---

    async def list_ports(self) -> Sequence[Port]:
        result = await self._session.execute(select(Port).order_by(Port.id))
        return result.scalars().all()

    async def get_port(self, port_id: int) -> Port | None:
        return await self._session.get(Port, port_id)
