"""Журнал фактических остановок портов и сверка с ним предиктора.

- Остановки фиксируют админы и доверенные источники (/closed, /reopened),
  исторические — админ (/closure с датами).
- Точность (/accuracy, GET /api/v1/accuracy): алерты warning+ против фактов
  по портам за N дней.
- Калибровка (/calibrate): подбор порогов ветра по размеченным наблюдениям.
  Подсказка, а не автопилот: пороги в .env меняет человек.
- Бэкфилл: исторический ветер Open-Meteo archive в weather_snapshots, чтобы
  сверять старые штормы (журнал можно заполнить задним числом).

Математика — в services/calibration.py (чистые функции).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AlertLevel, ClosureCause, Port, PortClosure
from app.db.repositories.calibration import CalibrationRepository
from app.integrations.weather.base import WeatherHistoryProvider, WindObservation
from app.services.calibration import (
    Calibration,
    EventScore,
    Interval,
    calibrate,
    label_samples,
    score_events,
)
from app.services.weather_predictor import WindThresholds

logger = structlog.get_logger(__name__)

ARCHIVE_SOURCE = "open-meteo-archive"
BACKFILL_CHUNK_DAYS = 92  # один запрос к архиву — не больше квартала часов
MAX_NOTE_LEN = 500


class ClosureError(ValueError):
    """Ошибка ввода для пользователя бота (текст — в сообщение)."""


def _utc(value: datetime) -> datetime:
    """SQLite отдаёт naive — приводим всё к aware UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ClosureInfo:
    port_code: str
    port_name: str
    started_at: datetime
    ended_at: datetime | None
    cause: ClosureCause

    @property
    def duration(self) -> timedelta | None:
        return self.ended_at - self.started_at if self.ended_at is not None else None


@dataclass(frozen=True, slots=True)
class PortAccuracy:
    code: str
    name: str
    score: EventScore


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    code: str
    name: str
    since: datetime
    until: datetime
    thresholds: WindThresholds
    result: Calibration


def _info(port: Port, closure: PortClosure) -> ClosureInfo:
    return ClosureInfo(
        port_code=port.code,
        port_name=port.name,
        started_at=_utc(closure.started_at),
        ended_at=_utc(closure.ended_at) if closure.ended_at is not None else None,
        cause=closure.cause,
    )


def _clean_note(note: str | None) -> str | None:
    note = (note or "").strip()
    return note[:MAX_NOTE_LEN] or None


class PredictorAccuracyService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        thresholds: WindThresholds,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._thresholds = thresholds
        self._clock = clock or (lambda: datetime.now(UTC))

    # --- журнал остановок -------------------------------------------------------------

    async def close_port(
        self,
        query: str,
        *,
        cause: ClosureCause = ClosureCause.wind,
        note: str | None = None,
        reported_by: int | None = None,
    ) -> ClosureInfo:
        """Порт встал сейчас. Повторное закрытие уже закрытого — ошибка, не дубль."""
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            port = await self._port(repo, query)
            if await repo.open_closure(port.id) is not None:
                raise ClosureError(f"{port.name}: остановка уже открыта — /reopened {port.code}")
            closure = await repo.add_closure(
                port.id, self._clock(), None, cause, _clean_note(note), reported_by
            )
            await session.commit()
            logger.info("port_closure_opened", port=port.code, cause=cause.value)
            return _info(port, closure)

    async def reopen_port(self, query: str) -> ClosureInfo:
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            port = await self._port(repo, query)
            closure = await repo.open_closure(port.id)
            if closure is None:
                raise ClosureError(f"{port.name}: открытой остановки нет")
            now = self._clock()
            closure.ended_at = max(now, _utc(closure.started_at))
            await session.commit()
            logger.info("port_closure_closed", port=port.code)
            return _info(port, closure)

    async def add_closure(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        cause: ClosureCause = ClosureCause.wind,
        note: str | None = None,
        reported_by: int | None = None,
    ) -> ClosureInfo:
        """Историческая остановка (из новостей, отчётов порта) — для калибровки задним числом."""
        started_at, ended_at = _utc(started_at), _utc(ended_at)
        if ended_at <= started_at:
            raise ClosureError("конец остановки должен быть позже начала")
        if ended_at > self._clock():
            raise ClosureError("остановка ещё не закончилась — используйте /closed")
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            port = await self._port(repo, query)
            overlap = await repo.closures(port.id, started_at, ended_at)
            if overlap:
                raise ClosureError(f"{port.name}: на эти даты остановка уже записана")
            closure = await repo.add_closure(
                port.id, started_at, ended_at, cause, _clean_note(note), reported_by
            )
            await session.commit()
            return _info(port, closure)

    # --- точность и калибровка --------------------------------------------------------

    async def accuracy(self, days: int = 90) -> list[PortAccuracy]:
        """Алерты warning+ против остановок по ветру — по каждому отслеживаемому порту."""
        until = self._clock()
        since = until - timedelta(days=days)
        out: list[PortAccuracy] = []
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            for port in await repo.tracked_ports():
                closures = await self._closure_intervals(repo, port, since, until)
                alerts = [
                    Interval(
                        _utc(a.opened_at), _utc(a.closed_at) if a.closed_at is not None else None
                    )
                    for a in await repo.alerts(
                        port.id, since, until, (AlertLevel.warning, AlertLevel.critical)
                    )
                ]
                score = score_events(closures, alerts, until)
                out.append(PortAccuracy(port.code, port.name, score))
        return out

    async def calibrate(self, query: str, days: int = 365) -> CalibrationReport:
        until = self._clock()
        since = until - timedelta(days=days)
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            port = await self._port(repo, query)
            closures = await self._closure_intervals(repo, port, since, until)
            observations = [
                (_utc(s.ts), s.wind_speed, s.wind_gust)
                for s in await repo.snapshots(port.id, since, until)
            ]
        th = self._thresholds
        result = calibrate(
            label_samples(observations, closures, until),
            closures=len(closures),
            warning=(th.warning_wind, th.warning_gust),
            critical=(th.critical_wind, th.critical_gust),
        )
        return CalibrationReport(port.code, port.name, since, until, th, result)

    # --- бэкфилл исторического ветра --------------------------------------------------

    async def backfill(
        self,
        provider: WeatherHistoryProvider,
        start: date,
        end: date,
        query: str | None = None,
    ) -> dict[str, int]:
        """Исторический ветер в weather_snapshots; уже записанные часы пропускаются."""
        if end < start:
            raise ClosureError("конец периода раньше начала")
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            ports = [await self._port(repo, query)] if query else list(await repo.tracked_ports())
        added: dict[str, int] = {}
        for port in ports:
            added[port.code] = 0
            chunk_start = start
            while chunk_start <= end:
                chunk_end = min(end, chunk_start + timedelta(days=BACKFILL_CHUNK_DAYS - 1))
                history = await provider.get_wind_history(
                    port.lat, port.lon, chunk_start, chunk_end
                )
                added[port.code] += await self._store_history(port, history)
                chunk_start = chunk_end + timedelta(days=1)
            logger.info("weather_backfill_done", port=port.code, added=added[port.code])
        return added

    async def _store_history(self, port: Port, history: list[WindObservation]) -> int:
        if not history:
            return 0
        lo, hi = history[0].ts, history[-1].ts
        async with self._session_factory() as session:
            repo = CalibrationRepository(session)
            known = {_utc(ts) for ts in await repo.snapshot_times(port.id, lo, hi)}
            fresh = [obs for obs in history if _utc(obs.ts) not in known]
            count = await repo.add_snapshots(port.id, fresh, ARCHIVE_SOURCE)
            await session.commit()
        return count

    # --- общее ------------------------------------------------------------------------

    @staticmethod
    async def _port(repo: CalibrationRepository, query: str | None) -> Port:
        port = await repo.find_port(query or "")
        if port is None:
            raise ClosureError(f"порт «{(query or '').strip()}» не найден")
        return port

    @staticmethod
    async def _closure_intervals(
        repo: CalibrationRepository, port: Port, since: datetime, until: datetime
    ) -> list[Interval]:
        return [
            Interval(_utc(c.started_at), _utc(c.ended_at) if c.ended_at is not None else None)
            for c in await repo.closures(port.id, since, until, cause=ClosureCause.wind)
        ]
