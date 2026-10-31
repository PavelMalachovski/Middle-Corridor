"""Демо-история груза MC-26-0398 — только при DEMO_CONTROL=true.

Остальной мок строится относительно «сейчас» и при переводе часов не
двигается. История привязана к моменту старта демо (MockClock.story_start),
поэтому ведущий переводит часы — и груз проходит путь: ждёт парома в Актау
под риском шторма → шторм, погодный запрет → погрузка на паром → Алят → … →
Констанца. Ветер в Актау подогнан под историю, чтобы карточка, прогноз и
вкладка «Коридор» не противоречили друг другу. Через PERIOD история
начинается заново.

Часы таймлайна — от T0 (старт цикла):
  −8      прибыл в Актау (по плану отход в +4)
  [−12, 6)  ветер в Актау 15/18 м/с — warning, ждём погрузки на паром
  [6, 66)   21/29 м/с — critical, погодный запрет на швартовку
  [66, 90)  11/14 м/с — watch, ветер стихает
  70      отход из Актау на пароме «Azerbaijan» (без AIS — проекция)
  220     прибыл в Констанцу — доставлен
  244     следующий цикл
"""

import math
from collections.abc import Callable
from datetime import datetime, timedelta

from app.integrations.mock.clock import MockClock
from app.integrations.mock.fleet import _DWELL_H, CARGO_EN, ROUTE_AKTAU
from app.services.corridor import NODES, segment
from app.services.demo_clock import DemoClockAction, DemoClockState
from app.services.queue_forecast import QueueInput
from app.services.tracking import EventKind, PlannedLeg, ShipmentPlan, TrackingEvent

H = timedelta(hours=1)

REF = "MC-26-0398"
CLIENT = "Steppe Freight KZ"
CARGO = "3 × 20', полипропилен"
FERRY = "Azerbaijan"
SEA_VESSEL = "Black Sea Link"
PORT = "AKTAU"

PERIOD = timedelta(hours=244)
BEAT_SETTLE = timedelta(minutes=1)  # «следующий шаг» встаёт чуть после такта
ARRIVE_PORT_H = -8.0
STORM_START_H = 6.0
STORM_END_H = 66.0
CALM_END_H = 90.0
WARNING_FROM_H = -12.0
DEPART_PORT_H = 70.0

WIND_WARNING = (15.0, 18.0)
WIND_CRITICAL = (21.0, 29.0)
WIND_CALMING = (11.0, 14.0)

QUEUE_POSITION = 4
QUEUE_PER_DAY = 8.0
FORECAST_H = 48

_VESSELS = {(PORT, "BAKU_ALAT"): FERRY, ("POTI", "CONSTANTA"): SEA_VESSEL}


def _dwell(code: str) -> float:
    return _DWELL_H[NODES[code].kind]


def _schedule(port_departure_h: float) -> tuple[dict[str, float], dict[str, float]]:
    """Часы прибытия и отправления по узлам при отходе из Актау в port_departure_h."""
    idx = ROUTE_AKTAU.index(PORT)
    arrive: dict[str, float] = {PORT: ARRIVE_PORT_H}
    depart: dict[str, float] = {PORT: port_departure_h}
    for i in range(idx, 0, -1):  # назад от Актау
        a, b = ROUTE_AKTAU[i - 1], ROUTE_AKTAU[i]
        depart[a] = arrive[b] - segment(a, b).typical_hours
        if i - 1 > 0:
            arrive[a] = depart[a] - _dwell(a)
    for i in range(idx, len(ROUTE_AKTAU) - 1):  # вперёд от Актау
        a, b = ROUTE_AKTAU[i], ROUTE_AKTAU[i + 1]
        arrive[b] = depart[a] + segment(a, b).typical_hours
        if i + 1 < len(ROUTE_AKTAU) - 1:
            depart[b] = arrive[b] + _dwell(b)
    return arrive, depart


_ACTUAL_ARRIVE, _ACTUAL_DEPART = _schedule(DEPART_PORT_H)
_PLAN_ARRIVE, _PLAN_DEPART = _schedule(ARRIVE_PORT_H + _dwell(PORT))


class DemoStory:
    """История 0398 от момента старта демо; story_start — из MockClock."""

    def __init__(self, story_start: Callable[[], datetime]) -> None:
        self._story_start = story_start

    def cycle_start(self, now: datetime) -> datetime:
        # начало часа: погода узлов округляется вниз (15 мин, прогноз — час), и
        # такт «шторм» не должен попасть в округление до шторма
        start = self._story_start().replace(minute=0, second=0, microsecond=0)
        if now < start:
            return start
        return start + math.floor((now - start) / PERIOD) * PERIOD

    def aktau_wind(self, ts: datetime) -> tuple[float, float] | None:
        """Ветер (скорость, порывы) в Актау по истории; None — история его не задаёт."""
        t0 = self.cycle_start(ts)
        for start in (t0, t0 + PERIOD):  # за 12 ч до следующего цикла — уже его warning
            h = (ts - start) / H
            if WARNING_FROM_H <= h < STORM_START_H:
                return WIND_WARNING
            if STORM_START_H <= h < STORM_END_H:
                return WIND_CRITICAL
            if STORM_END_H <= h < CALM_END_H:
                return WIND_CALMING
        return None

    def beats(self, now: datetime) -> list[datetime]:
        """Такты текущего цикла для «следующего шага»: начало шторма и события."""
        t0 = self.cycle_start(now)
        events = [e.ts for e in self.plan(now).events if e.ts >= t0]
        return sorted({t0 + STORM_START_H * H, *events})

    def plan(self, now: datetime) -> ShipmentPlan:
        t0 = self.cycle_start(now)
        at = lambda hours: t0 + hours * H  # noqa: E731 — локальный короткий помощник
        route = ROUTE_AKTAU
        legs = tuple(
            PlannedLeg(
                from_code=a,
                to_code=b,
                depart_at=at(_PLAN_DEPART[a]),
                arrive_at=at(_PLAN_ARRIVE[b]),
                vessel=_VESSELS.get((a, b)),
            )
            for a, b in zip(route, route[1:], strict=False)
        )
        events: list[TrackingEvent] = []
        for i, code in enumerate(route):
            if i > 0:
                events.append(TrackingEvent(EventKind.arrived, code, at(_ACTUAL_ARRIVE[code])))
            if i < len(route) - 1:
                vessel = _VESSELS.get((code, route[i + 1]))
                note, note_code = None, None
                if vessel == FERRY:
                    note, note_code = f"погружен на паром «{vessel}»", "loaded_on_ferry"
                elif vessel:
                    note, note_code = f"погружен на судно «{vessel}»", "loaded_on_vessel"
                events.append(
                    TrackingEvent(
                        EventKind.departed,
                        code,
                        at(_ACTUAL_DEPART[code]),
                        note,
                        note_code=note_code,
                        note_vessel=vessel,
                    )
                )

        storm = at(STORM_START_H) <= now
        if storm:
            hold = {
                "hold_reason": "Погодный запрет на швартовку: Актау — критический ветер",
                "hold_code": "weather_ban",
                "hold_node": PORT,
                "hold_vessel": None,
            }
        else:
            hold = {
                "hold_reason": f"Ожидание погрузки на паром «{FERRY}»",
                "hold_code": "ferry_loading_wait",
                "hold_node": PORT,
                "hold_vessel": FERRY,
            }
        weather_hours = sum(
            1 for i in range(FORECAST_H) if at(STORM_START_H) <= now + i * H < at(STORM_END_H)
        )
        return ShipmentPlan(
            ref=REF,
            client=CLIENT,
            cargo=CARGO,
            cargo_en=CARGO_EN.get(CARGO),
            legs=legs,
            events=tuple(sorted(events, key=lambda e: e.ts)),
            queue=QueueInput(
                PORT,
                QUEUE_POSITION,
                QUEUE_PER_DAY,
                float(weather_hours),
                "weather_ban" if storm else "ferry_wait",
            ),
            **hold,
        )


class DemoControl:
    """Пульт ведущего: перевод мок-часов и шаги истории (/api/v1/demo/clock)."""

    def __init__(self, clock: MockClock, story: DemoStory) -> None:
        self._clock = clock
        self._story = story

    def state(self) -> DemoClockState:
        return DemoClockState(
            now=self._clock.now(),
            offset_hours=round(self._clock.offset / H, 3),
            story_start=self._clock.story_start,
            story_ref=REF,
        )

    def apply(self, action: DemoClockAction) -> DemoClockState:
        if action.action == "advance":
            self._clock.advance(action.hours or 0.0)
        elif action.action == "reset":
            self._clock.reset()
        else:
            now = self._clock.now()
            upcoming = [beat for beat in self._story.beats(now) if beat > now]
            if upcoming:
                self._clock.jump_to(upcoming[0] + BEAT_SETTLE)
            else:  # история кончилась — начало следующего цикла
                self._clock.jump_to(self._story.cycle_start(now) + PERIOD)
        return self.state()
