"""Мок-часы: виртуальное время, при необходимости ускоренное для демо."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta


def _wall() -> datetime:
    return datetime.now(UTC)


class MockClock:
    """virtual_now = anchor + (real_now - anchor) * scale + offset.

    scale=1 — обычное время; scale=60 — час мок-времени за минуту: паром
    пересекает Каспий за 20 минут, а не за 20 часов. offset — перевод часов
    ведущим демо (/api/v1/demo/clock); story_start — момент, от которого
    отсчитывается демо-история груза (сбрасывается вместе с часами).
    """

    def __init__(
        self,
        scale: float = 1.0,
        anchor: datetime | None = None,
        real: Callable[[], datetime] | None = None,
    ) -> None:
        self._scale = scale
        self._real = real or _wall
        self._anchor = anchor or self._real()
        self.offset = timedelta(0)
        self.story_start = self.now()

    def now(self) -> datetime:
        real = self._real()
        return self._anchor + (real - self._anchor) * self._scale + self.offset

    def advance(self, hours: float) -> None:
        self.offset += timedelta(hours=hours)

    def jump_to(self, ts: datetime) -> None:
        self.offset += ts - self.now()

    def reset(self) -> None:
        self.offset = timedelta(0)
        self._anchor = self._real()
        self.story_start = self.now()
