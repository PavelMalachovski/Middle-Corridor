"""Мок-флот Каспия и мок-отправки.

Паромы ASCO ходят по циклу Курык/Актау ↔ Алят: 8 ч погрузка → 20 ч переход →
8 ч в Аляте → 20 ч обратно (56 ч). Фаза каждого парома сдвинута, поэтому в
любой момент кто-то в море, кто-то у причала. Два парома намеренно «вне
AIS» — как в жизни на Каспии: у них нет позиции, а не «стоят».

Отправок в публичном демо две, обе строятся относительно текущего момента:
MC-26-0501 — настоящий маршрут автокомплектов Škoda Млада-Болеслав → … → Алят →
Актау → Костанай (данные обезличены), цикл 112 ч на рейсах парома «Shahdag»
(только вперёд: Алят → паром → Актау → Бейнеу → к Костанаю → заново, без «доставлен»);
MC-26-0431 — пример «возможна санкционка» на рельсах в степи. Под DEMO_CONTROL
0501 заменяет история (story.py). Положение считает services.tracking.
"""

import dataclasses
import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.integrations.mock.packing import with_packing
from app.services.corridor import NODES, segment
from app.services.geo import point_along
from app.services.map_snapshot import VesselMapStatus
from app.services.queue_forecast import QueueInput
from app.services.schedule import leg_offsets, plan_legs
from app.services.tracking import EventKind, ShipmentPlan, TrackingEvent

if TYPE_CHECKING:
    from app.integrations.mock.story import DemoStory

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
CYCLE_H = 56.0
_LOAD_EAST_END = 8.0
_SAIL_WEST_END = 28.0
_AT_ALAT_END = 36.0
SAIL_H = 20.0
SPEED_KN = 10.5


@dataclass(frozen=True, slots=True)
class FerrySpec:
    name: str
    east_port: str  # KURYK | AKTAU
    offset_h: float  # фаза цикла
    has_ais: bool
    mmsi: int | None


# AIS-паромы стоят с шагом 11 ч < 20 ч перехода: в любой момент хотя бы
# один из них идёт на запад — на него всегда можно «посадить» груз.
FERRIES: tuple[FerrySpec, ...] = (
    FerrySpec("Professor Gul", "KURYK", 0.0, True, 423123001),
    FerrySpec("Academician Zarifa Aliyeva", "KURYK", 11.0, True, 423123002),
    FerrySpec("Azerbaijan", "AKTAU", 6.0, False, None),
    FerrySpec("Barda", "KURYK", 22.0, True, 423123004),
    FerrySpec("Balaken", "KURYK", 50.0, False, None),
    FerrySpec("Shahdag", "AKTAU", 33.0, True, 423123006),
    FerrySpec("Fikret Amirov", "KURYK", 44.0, True, 423123007),
)


@dataclass(frozen=True, slots=True)
class FerryState:
    spec: FerrySpec
    lat: float
    lon: float
    sog: float
    cog: float
    sailing: bool
    westbound: bool  # текущий (или ближайший) рейс — на Алят
    from_code: str
    to_code: str
    sail_start: datetime  # текущий или ближайший рейс
    sail_end: datetime
    phase: str
    phase_code: str  # at_sea | in_port


def _seed(*parts: str) -> int:
    return int(hashlib.sha1("|".join(parts).encode()).hexdigest()[:8], 16)


def ferry_state(spec: FerrySpec, now: datetime) -> FerryState:
    hours = (now - _EPOCH).total_seconds() / 3600.0
    pos = (hours + spec.offset_h) % CYCLE_H
    cycle_start = now - timedelta(hours=pos)

    if pos < _LOAD_EAST_END:  # грузимся в восточном порту, ближайший рейс — на запад
        start, end = _LOAD_EAST_END, _SAIL_WEST_END
        sailing, westbound, frac = False, True, 0.0
    elif pos < _SAIL_WEST_END:
        start, end = _LOAD_EAST_END, _SAIL_WEST_END
        sailing, westbound, frac = True, True, (pos - _LOAD_EAST_END) / SAIL_H
    elif pos < _AT_ALAT_END:  # у причала в Аляте, ближайший рейс — на восток
        start, end = _AT_ALAT_END, CYCLE_H
        sailing, westbound, frac = False, False, 0.0
    else:
        start, end = _AT_ALAT_END, CYCLE_H
        sailing, westbound, frac = True, False, (pos - _AT_ALAT_END) / SAIL_H

    from_code, to_code = (
        (spec.east_port, "BAKU_ALAT") if westbound else ("BAKU_ALAT", spec.east_port)
    )
    seg = segment(from_code, to_code)
    if sailing:
        (lat, lon), cog = point_along(seg.points, frac)
        sog = SPEED_KN + ((_seed(spec.name, str(int(hours))) % 100) / 100.0 - 0.5)
        phase = "в море"
        phase_code = "at_sea"
    else:
        node = NODES[from_code]
        lat, lon, cog, sog = node.lat, node.lon, 0.0, 0.0
        phase = f"в порту {node.name}"
        phase_code = "in_port"
    return FerryState(
        spec=spec,
        lat=round(lat, 4),
        lon=round(lon, 4),
        sog=round(sog, 1),
        cog=round(cog),
        sailing=sailing,
        westbound=westbound,
        from_code=from_code,
        to_code=to_code,
        sail_start=cycle_start + timedelta(hours=start),
        sail_end=cycle_start + timedelta(hours=end),
        phase=phase,
        phase_code=phase_code,
    )


def list_ferry_states(now: datetime) -> list[FerryState]:
    return [ferry_state(spec, now) for spec in FERRIES]


class MockFleetSource:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def list_vessels(self, at: datetime | None = None) -> list[VesselMapStatus]:
        now = at or self._clock()
        result: list[VesselMapStatus] = []
        for state in list_ferry_states(now):
            spec = state.spec
            if not spec.has_ais:
                # Честное «нет данных»: ни позиции, ни маршрута — мы этого не знаем
                result.append(VesselMapStatus(name=spec.name, operator="ASCO"))
                continue
            age_min = 1 + _seed(spec.name, str(int(now.timestamp() // 600))) % 9
            result.append(
                VesselMapStatus(
                    name=spec.name,
                    operator="ASCO",
                    mmsi=spec.mmsi,
                    lat=state.lat,
                    lon=state.lon,
                    sog=state.sog,
                    cog=state.cog,
                    ts=now - timedelta(minutes=age_min),
                    has_recent_data=True,
                    route=f"{NODES[state.from_code].name} → {NODES[state.to_code].name}",
                    phase=state.phase,
                    from_code=state.from_code,
                    to_code=state.to_code,
                    phase_code=state.phase_code,
                    phase_node=None if state.sailing else state.from_code,
                )
            )
        return result


# --- Отправки ------------------------------------------------------------------

ROUTE_KURYK = [
    "XIAN", "URUMQI", "KHORGOS", "ALMATY", "SHYMKENT", "KYZYLORDA", "BEINEU", "KURYK",
    "BAKU_ALAT", "GANJA", "BOYUK_KASIK", "TBILISI", "POTI", "CONSTANTA", "BUCHAREST", "BUDAPEST",
]  # fmt: skip
# Европа → Казахстан (на восток): завод → порт Копер → перевалка в Амбарлы → Поти → … → Костанай
ROUTE_KOSTANAY = [
    "MLADA_BOLESLAV", "KOPER", "AMBARLI", "POTI", "TBILISI", "BOYUK_KASIK", "GANJA",
    "BAKU_ALAT", "AKTAU", "BEINEU", "KOSTANAY",
]  # fmt: skip


_FERRY_NAMES = {spec.name for spec in FERRIES}


def _jitter_h(ref: str, code: str, kind: str) -> float:
    return ((_seed(ref, code, kind) % 7) - 3) * 0.5  # −1.5…+1.5 ч, детерминировано


# Описания грузов мока по-английски: карта в EN показывает их вместо русских
CARGO_EN: dict[str, str] = {
    "1 × 40' HC, автозапчасти": "1 × 40' HC, auto parts",
    "1 × 40' HC, автокомплекты": "1 × 40' HC, car assembly kits",
}

EAST_REF = "MC-26-0501"
EAST_CLIENT = "Steppe Auto Assembly"
EAST_CARGO = "1 × 40' HC, автокомплекты"
EAST_FERRY = "Shahdag"  # единственный AIS-паром мок-флота на линии Алят — Актау
EAST_DELAY_H = 10.0  # паром из Алята ушёл позже плана: в демо есть груз «с задержкой»


def build_plan(  # noqa: PLR0913 — сценарий описывается параметрами
    ref: str,
    client: str,
    cargo: str,
    route: list[str],
    pivot_kind: EventKind,
    pivot_code: str,
    pivot_ts: datetime,
    *,
    delay_hours: float = 0.0,
    vessels: dict[tuple[str, str], str] | None = None,
    hold_reason: str | None = None,
    hold_code: str | None = None,
    hold_node: str | None = None,
    hold_vessel: str | None = None,
    pivot_note: str | None = None,
    pivot_note_code: str | None = None,
    queue: QueueInput | None = None,
) -> ShipmentPlan:
    """План по типичным временам сегментов, «пришпиленный» к опорному событию.

    Опорное событие (pivot) — последнее подтверждённое; его плановое время =
    фактическое минус delay_hours, от него раскладывается всё расписание.
    """
    vessels = vessels or {}
    depart, arrive = leg_offsets(route)
    pivot_offset = depart[pivot_code] if pivot_kind == EventKind.departed else arrive[pivot_code]
    base = pivot_ts - timedelta(hours=delay_hours + pivot_offset)

    legs = plan_legs(route, base, vessels)

    events: list[TrackingEvent] = []
    pivot_idx = route.index(pivot_code)
    for idx, code in enumerate(route[: pivot_idx + 1]):
        is_pivot = idx == pivot_idx
        if idx > 0:
            if is_pivot and pivot_kind == EventKind.arrived:
                events.append(
                    TrackingEvent(
                        EventKind.arrived, code, pivot_ts, pivot_note, note_code=pivot_note_code
                    )
                )
                break
            ts = base + timedelta(hours=arrive[code] + _jitter_h(ref, code, "arr"))
            events.append(TrackingEvent(EventKind.arrived, code, ts))
        next_code = route[idx + 1]
        vessel = vessels.get((code, next_code))
        note = None
        note_code = None
        if vessel:
            kind = "паром" if vessel in _FERRY_NAMES else "судно"
            note = f"погружен на {kind} «{vessel}»"
            note_code = "loaded_on_ferry" if vessel in _FERRY_NAMES else "loaded_on_vessel"
        if is_pivot:
            events.append(
                TrackingEvent(
                    EventKind.departed,
                    code,
                    pivot_ts,
                    pivot_note or note,
                    note_code=pivot_note_code if pivot_note else note_code,
                    note_vessel=vessel,
                )
            )
        else:
            ts = base + timedelta(hours=depart[code] + _jitter_h(ref, code, "dep"))
            events.append(
                TrackingEvent(
                    EventKind.departed, code, ts, note, note_code=note_code, note_vessel=vessel
                )
            )

    return ShipmentPlan(
        ref=ref,
        client=client,
        cargo=cargo,
        cargo_en=CARGO_EN.get(cargo),
        legs=legs,
        events=tuple(sorted(events, key=lambda e: e.ts)),
        hold_reason=hold_reason,
        hold_code=hold_code,
        hold_node=hold_node,
        hold_vessel=hold_vessel,
        queue=queue,
    )


EAST_WAIT_H = 16.0  # ждёт в Аляте до отхода парома (начало цикла груза)
EAST_CYCLE_H = 2 * CYCLE_H  # Алят → Костанай (≈ 88 ч) не влезает в один рейс парома
# После отхода из Алята: паром (рейс «Shahdag»), стоянка в Актау, рельсы, Бейнеу. Прибытия
# в Костанай в публичном демо нет: цикл перезапускается на подходе (D + 96 ч, плечо на 8 ч
# дольше плана) — «доставлен» скрыл бы груз из фильтра «с задержкой»; доставку показывает
# история пульта (DEMO_CONTROL)
_EAST_AFTER = (
    (EventKind.arrived, "AKTAU", SAIL_H),
    (EventKind.departed, "AKTAU", SAIL_H + 12.0),
    (EventKind.arrived, "BEINEU", SAIL_H + 22.0),
    (EventKind.departed, "BEINEU", SAIL_H + 28.0),
)


def east_departure(now: datetime) -> datetime:
    """Отход «Shahdag» из Алята, к которому привязан текущий цикл 0501.

    Цикл груза — два цикла парома (112 ч): [отход − 16 ч, отход + 96 ч). Берём каждый
    второй восточный рейс, поэтому за цикл груз проходит путь только вперёд: Алят →
    паром → Актау → Бейнеу → на подходе к Костанаю → новый цикл («доставлен» не бывает).
    """
    spec = next(f for f in FERRIES if f.name == EAST_FERRY)
    first = _EPOCH + timedelta(hours=_AT_ALAT_END - spec.offset_h)  # отход на восток
    hours = (now - first).total_seconds() / 3600.0 + EAST_WAIT_H
    return first + timedelta(hours=math.floor(hours / EAST_CYCLE_H) * EAST_CYCLE_H)


def east_plan(now: datetime) -> ShipmentPlan:
    """MC-26-0501 (Škoda → Костанай, данные обезличены) на цикле парома «Shahdag».

    Ждёт парома в Аляте → на «Shahdag» (позиция — AIS парома) → Актау → рельсы на
    Бейнеу → Костанай; задержка ≥ 10 ч на всём пути (в демо есть груз «с задержкой»).
    """
    depart = east_departure(now)
    arrive_alat = depart - timedelta(hours=EAST_WAIT_H)
    hold: dict[str, str | None] = {}
    if now < depart:
        at_alat = depart - now <= timedelta(hours=_AT_ALAT_END - _SAIL_WEST_END)
        hold = {
            "hold_reason": (
                f"Ожидание погрузки на паром «{EAST_FERRY}»"
                if at_alat
                else f"Ожидание парома «{EAST_FERRY}» с обратного рейса"
            ),
            "hold_code": "ferry_loading_wait" if at_alat else "ferry_return_wait",
            "hold_vessel": EAST_FERRY,
        }
    plan = build_plan(
        EAST_REF,
        EAST_CLIENT,
        EAST_CARGO,
        ROUTE_KOSTANAY,
        EventKind.arrived,
        "BAKU_ALAT",
        arrive_alat,
        delay_hours=EAST_DELAY_H,
        vessels={("BAKU_ALAT", "AKTAU"): EAST_FERRY},
        **hold,
    )
    after = [
        TrackingEvent(
            EventKind.departed,
            "BAKU_ALAT",
            depart,
            f"погружен на паром «{EAST_FERRY}»",
            note_code="loaded_on_ferry",
            note_vessel=EAST_FERRY,
        ),
        *(TrackingEvent(kind, code, depart + timedelta(hours=h)) for kind, code, h in _EAST_AFTER),
    ]
    return dataclasses.replace(plan, events=plan.events + tuple(after))


class MockShipmentSource:
    """Публичное демо — два груза: 0501 (восток, на Костанай) и 0431 (пример санкционки)."""

    def __init__(self, clock: Callable[[], datetime], story: "DemoStory | None" = None) -> None:
        self._clock = clock
        self._story = story  # демо-история 0501 (DEMO_CONTROL) вместо «вечного» сценария

    async def list_plans(self, at: datetime | None = None) -> list[ShipmentPlan]:
        now = at or self._clock()

        # 1. Восток: в демо-режиме — история с бурей в Актау, иначе — цикл на «Shahdag»
        east = self._story.plan(now) if self._story is not None else east_plan(now)

        # 2. Рельсы в степи: Кызылорда → Бейнеу, 16 ч из 26 в пути; в пакинг-листе — сталь
        #    российского происхождения → «возможна санкционка»
        steppe = build_plan(
            "MC-26-0431",
            "Nomad Express",
            "1 × 40' HC, автозапчасти",
            ROUTE_KURYK,
            EventKind.departed,
            "KYZYLORDA",
            now - timedelta(hours=16),
        )
        return [with_packing(p, now) for p in (east, steppe)]
