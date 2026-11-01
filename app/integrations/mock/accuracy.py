"""Мок-точность предиктора для демо: синтетическая история штормов по портам.

Не поле ветра карты: оно держит Курык и Актау в critical почти всё время, а
Баку и Констанцу — без тревог, и честная сверка по нему дала бы бессмысленные
цифры. Здесь — правдоподобные шторма (Каспий чаще, Чёрное море реже): большая
часть предсказана за 6–24 ч, часть тревог ложные, часть остановок пропущена.
Счёт — тот же `score_events`, что и в боевой сверке; в ответе API `demo: true`.
"""

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from app.services.calibration import Interval, score_events
from app.services.corridor import NODES, CorridorLeg, NodeKind
from app.services.predictor_accuracy import PortAccuracy

_EPOCH = datetime(2026, 1, 5, tzinfo=UTC)  # понедельник: недели считаются от него
WEEK = timedelta(days=7)
H = timedelta(hours=1)

PREDICTED_PCT = 70  # остановка с тревогой заранее
FALSE_ALARM_PCT = 15  # тревога без остановки; остаток — пропуск (остановка без тревоги)


def _seed(*parts: object) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _wall() -> datetime:
    return datetime.now(UTC)


class MockAccuracySource:
    """Тот же интерфейс, что у PredictorAccuracyService.accuracy — для /api/v1/accuracy."""

    demo = True

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        storms_per_week: Mapping[str, int] | None = None,
    ) -> None:
        self._clock = clock or _wall
        self._override = dict(storms_per_week or {})

    def _max_storms(self, code: str) -> int:
        if code in self._override:
            return self._override[code]
        return 2 if NODES[code].leg == CorridorLeg.caspian else 1

    def _history(
        self, code: str, since: datetime, until: datetime
    ) -> tuple[list[Interval], list[Interval]]:
        closures: list[Interval] = []
        alerts: list[Interval] = []
        first = int((since - _EPOCH) / WEEK) - 1
        last = int((until - _EPOCH) / WEEK) + 1
        for week in range(first, last + 1):
            week_start = _EPOCH + week * WEEK
            for i in range(_seed(code, week) % (self._max_storms(code) + 1)):
                s = _seed(code, week, i)
                start = week_start + (s % 168) * H
                duration = (6 + (s >> 8) % 31) * H
                lead = (6 + (s >> 16) % 19) * H
                kind = (s >> 24) % 100
                if not since <= start < until:
                    continue
                if kind < PREDICTED_PCT:
                    closures.append(Interval(start, start + duration))
                    alerts.append(Interval(start - lead, start + duration))
                elif kind < PREDICTED_PCT + FALSE_ALARM_PCT:
                    alerts.append(Interval(start - lead, start + duration / 2))
                else:
                    closures.append(Interval(start, start + duration))
        return closures, alerts

    async def accuracy(self, days: int = 90) -> list[PortAccuracy]:
        # начало суток: цифры не прыгают в течение дня и не зависят от перевода часов демо
        until = self._clock().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        since = until - timedelta(days=days)
        out: list[PortAccuracy] = []
        for code, node in NODES.items():
            if node.kind != NodeKind.port:
                continue
            closures, alerts = self._history(code, since, until)
            out.append(PortAccuracy(code, node.name, score_events(closures, alerts, until)))
        return out
