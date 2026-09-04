"""Мок-часы: виртуальное время, при необходимости ускоренное для демо."""

from datetime import UTC, datetime


class MockClock:
    """virtual_now = anchor + (real_now - anchor) * scale.

    scale=1 — обычное время; scale=60 — час мок-времени за минуту: паром
    пересекает Каспий за 20 минут, а не за 20 часов.
    """

    def __init__(self, scale: float = 1.0, anchor: datetime | None = None) -> None:
        self._scale = scale
        self._anchor = anchor or datetime.now(UTC)

    def now(self) -> datetime:
        real = datetime.now(UTC)
        return self._anchor + (real - self._anchor) * self._scale
