"""Снимки прогноза ветра по сетке над морями (поле ветра карты)."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WindGrid


class WindGridRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        fetched_at: datetime,
        step_deg: float,
        hours: list[str],
        points: list[dict[str, Any]],
        source: str = "open-meteo",
    ) -> WindGrid:
        row = WindGrid(
            fetched_at=fetched_at, step_deg=step_deg, hours=hours, points=points, source=source
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest(self, before: datetime | None = None) -> WindGrid | None:
        """Последний снимок; before — последний из взятых не позже этого момента."""
        stmt = select(WindGrid).order_by(WindGrid.fetched_at.desc()).limit(1)
        if before is not None:
            stmt = stmt.where(WindGrid.fetched_at <= before)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def earliest(self) -> WindGrid | None:
        result = await self._session.execute(
            select(WindGrid).order_by(WindGrid.fetched_at.asc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_older_than(self, ts: datetime) -> int:
        result = await self._session.execute(delete(WindGrid).where(WindGrid.fetched_at < ts))
        return int(result.rowcount or 0)
