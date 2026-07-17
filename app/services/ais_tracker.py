"""AIS-модуль (§7.2): обработка позиций и событий портов + стрим-воркер.

Честность прежде всего: покрытие AIS на Каспии слабое, поэтому
- разрывы стрима — норма: воркер переподключается с экспоненциальным
  backoff и не роняет процесс;
- позиции пишутся с троттлингом (не чаще раза в N минут на судно);
- давно не видели судно → в статусе это «нет данных», а не «стоит».
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import PortEventType, PositionSource
from app.db.repositories.ais import AISRepository
from app.integrations.ais.base import AISPosition, AISStreamProvider, BoundingBox

logger = structlog.get_logger(__name__)


class AISTrackerService:
    """Приём позиций/событий: фильтр по нашим судам, троттлинг, запись в БД."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        min_save_interval: timedelta = timedelta(minutes=5),
    ) -> None:
        self._session_factory = session_factory
        self._min_save_interval = min_save_interval
        self._mmsi_to_vessel_id: dict[int, int] | None = None
        self._last_saved: dict[int, datetime] = {}

    async def refresh_tracked(self) -> list[int]:
        """Перечитывает из БД отслеживаемые суда с MMSI; возвращает список MMSI."""
        async with self._session_factory() as session:
            vessels = await AISRepository(session).tracked_vessels_with_mmsi()
        self._mmsi_to_vessel_id = {v.mmsi: v.id for v in vessels if v.mmsi is not None}
        return list(self._mmsi_to_vessel_id)

    async def handle_position(
        self, position: AISPosition, source: PositionSource = PositionSource.aisstream
    ) -> bool:
        """Сохраняет позицию отслеживаемого судна. True — если записали."""
        if self._mmsi_to_vessel_id is None:
            await self.refresh_tracked()
        vessel_id = (self._mmsi_to_vessel_id or {}).get(position.mmsi)
        if vessel_id is None:
            return False  # не наше судно

        last = self._last_saved.get(position.mmsi)
        if last is not None and position.ts - last < self._min_save_interval:
            return False  # троттлинг: паромы шлют позицию каждые несколько секунд

        async with self._session_factory() as session:
            await AISRepository(session).add_position(vessel_id, position, source)
            await session.commit()
        self._last_saved[position.mmsi] = position.ts
        logger.info(
            "ais_position_saved",
            mmsi=position.mmsi,
            lat=round(position.lat, 4),
            lon=round(position.lon, 4),
            sog=position.sog,
        )
        return True

    async def handle_port_event(
        self,
        mmsi: int,
        port_code: str,
        event_type: PortEventType,
        ts: datetime | None,
        source: PositionSource = PositionSource.vesselapi,
    ) -> bool:
        """Сохраняет заход/отход. False — если судно или порт неизвестны."""
        async with self._session_factory() as session:
            repo = AISRepository(session)
            vessel = await repo.get_vessel_by_mmsi(mmsi)
            port = await repo.get_port_by_code(port_code)
            if vessel is None or port is None:
                logger.warning(
                    "ais_port_event_ignored",
                    mmsi=mmsi,
                    port_code=port_code,
                    known_vessel=vessel is not None,
                    known_port=port is not None,
                )
                return False
            await repo.add_port_event(
                port.id, vessel.id, event_type, ts or datetime.now(UTC), source
            )
            await session.commit()
        logger.info("ais_port_event_saved", mmsi=mmsi, port=port_code, event_type=event_type.value)
        return True


class AISStreamWorker:
    """Долгоживущий воркер стрима с авто-reconnect и экспоненциальным backoff."""

    def __init__(
        self,
        provider: AISStreamProvider,
        tracker: AISTrackerService,
        boxes: list[BoundingBox],
        initial_delay: float = 1.0,
        max_delay: float = 300.0,
    ) -> None:
        self._provider = provider
        self._tracker = tracker
        self._boxes = boxes
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self.last_message_at: datetime | None = None  # метрика живости стрима

    async def run(self) -> None:
        """Крутится до отмены таски; любые ошибки стрима → reconnect."""
        delay = self._initial_delay
        while True:
            try:
                mmsi_filter = await self._tracker.refresh_tracked()
                if not mmsi_filter:
                    logger.info(
                        "ais_no_tracked_mmsi",
                        detail="MMSI судов не заполнены — слушаем bbox для метрики живости",
                    )
                async for position in self._provider.stream(self._boxes, mmsi_filter or None):
                    self.last_message_at = datetime.now(UTC)
                    delay = self._initial_delay  # поток жив — сбросить backoff
                    await self._tracker.handle_position(position)
                logger.warning("ais_stream_ended", detail="сервер закрыл стрим")
            except asyncio.CancelledError:
                logger.info("ais_worker_cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 — воркер не должен падать
                logger.warning("ais_stream_disconnected", error=str(exc), retry_in_s=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_delay)
