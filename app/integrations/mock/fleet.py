"""Мок-флот Каспия и мок-отправки.

Паромы ASCO ходят по циклу Курык/Актау ↔ Алят: 8 ч погрузка → 20 ч переход →
8 ч в Аляте → 20 ч обратно (56 ч). Фаза каждого парома сдвинута, поэтому в
любой момент кто-то в море, кто-то у причала. Два парома намеренно «вне
AIS» — как в жизни на Каспии: у них нет позиции, а не «стоят».

Отправки строятся относительно текущего момента: у каждой — сценарий
(в море на пароме, ждёт погоды в Актау, на рельсах в степи, на таможне…),
план и подтверждённые события. Положение считает services.tracking.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.services.corridor import NODES, NodeKind, segment
from app.services.geo import point_along
from app.services.map_snapshot import VesselMapStatus
from app.services.tracking import EventKind, PlannedLeg, ShipmentPlan, TrackingEvent

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

_DWELL_H = {NodeKind.rail: 6.0, NodeKind.port: 12.0, NodeKind.border: 18.0}

ROUTE_KURYK = [
    "XIAN", "URUMQI", "KHORGOS", "ALMATY", "SHYMKENT", "KYZYLORDA", "BEINEU", "KURYK",
    "BAKU_ALAT", "GANJA", "BOYUK_KASIK", "TBILISI", "POTI", "CONSTANTA", "BUCHAREST", "BUDAPEST",
]  # fmt: skip
ROUTE_AKTAU = [
    "XIAN", "URUMQI", "KHORGOS", "ALMATY", "SHYMKENT", "KYZYLORDA", "BEINEU", "AKTAU",
    "BAKU_ALAT", "GANJA", "BOYUK_KASIK", "TBILISI", "POTI", "CONSTANTA",
]  # fmt: skip
ROUTE_BATUMI = [
    "URUMQI", "KHORGOS", "ALMATY", "SHYMKENT", "KYZYLORDA", "BEINEU", "KURYK", "BAKU_ALAT",
    "GANJA", "BOYUK_KASIK", "TBILISI", "BATUMI", "CONSTANTA", "BUCHAREST",
]  # fmt: skip


_FERRY_NAMES = {spec.name for spec in FERRIES}


def _jitter_h(ref: str, code: str, kind: str) -> float:
    return ((_seed(ref, code, kind) % 7) - 3) * 0.5  # −1.5…+1.5 ч, детерминировано


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
) -> ShipmentPlan:
    """План по типичным временам сегментов, «пришпиленный» к опорному событию.

    Опорное событие (pivot) — последнее подтверждённое; его плановое время =
    фактическое минус delay_hours, от него раскладывается всё расписание.
    """
    vessels = vessels or {}
    depart: dict[str, float] = {route[0]: 0.0}
    arrive: dict[str, float] = {}
    t = 0.0
    for a, b in zip(route, route[1:], strict=False):
        t += segment(a, b).typical_hours
        arrive[b] = t
        t += _DWELL_H[NODES[b].kind]
        depart[b] = t

    pivot_offset = depart[pivot_code] if pivot_kind == EventKind.departed else arrive[pivot_code]
    base = pivot_ts - timedelta(hours=delay_hours + pivot_offset)

    legs = tuple(
        PlannedLeg(
            from_code=a,
            to_code=b,
            depart_at=base + timedelta(hours=depart[a]),
            arrive_at=base + timedelta(hours=arrive[b]),
            vessel=vessels.get((a, b)),
        )
        for a, b in zip(route, route[1:], strict=False)
    )

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
        legs=legs,
        events=tuple(sorted(events, key=lambda e: e.ts)),
        hold_reason=hold_reason,
        hold_code=hold_code,
        hold_node=hold_node,
        hold_vessel=hold_vessel,
    )


class MockShipmentSource:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def list_plans(self, at: datetime | None = None) -> list[ShipmentPlan]:
        now = at or self._clock()
        h = timedelta(hours=1)
        ferries = {state.spec.name: state for state in list_ferry_states(now)}

        # 1. На AIS-пароме посреди Каспия: самый «продвинутый» западный рейс
        west = [f for f in ferries.values() if f.sailing and f.westbound and f.spec.has_ais]
        f1 = min(west, key=lambda f: f.sail_start)
        route1 = ROUTE_KURYK if f1.spec.east_port == "KURYK" else ROUTE_AKTAU
        on_ferry = build_plan(
            "MC-26-0412",
            "Silk Road Forwarders",
            "2 × 40' HC, электроника",
            route1,
            EventKind.departed,
            f1.from_code,
            f1.sail_start,
            vessels={(f1.from_code, "BAKU_ALAT"): f1.spec.name},
        )

        # 2. Ждёт погоды в Актау: план предполагал отход 18 ч назад
        weather_hold = build_plan(
            "MC-26-0398",
            "Steppe Freight KZ",
            "3 × 20', полипропилен",
            ROUTE_AKTAU,
            EventKind.arrived,
            "AKTAU",
            now - 30 * h,
            hold_reason="Погодный запрет на швартовку: Актау — критический ветер",
            hold_code="weather_ban",
            hold_node="AKTAU",
        )

        # 3. Рельсы в степи: Кызылорда → Бейнеу, 16 ч из 26 в пути
        steppe = build_plan(
            "MC-26-0431",
            "Nomad Express",
            "1 × 40' HC, автозапчасти",
            ROUTE_KURYK,
            EventKind.departed,
            "KYZYLORDA",
            now - 16 * h,
        )

        # 4. Таможня на границе AZ/GE
        customs = build_plan(
            "MC-26-0377",
            "Kür Logistics",
            "2 × 40', солнечные панели",
            ROUTE_KURYK,
            EventKind.arrived,
            "BOYUK_KASIK",
            now - 20 * h,
            hold_reason="Таможенное оформление AZ/GE — ожидание досмотра",
            hold_code="customs_wait",
            hold_node="BOYUK_KASIK",
        )

        # 5. Поти, ждёт ро-ро на Констанцу по плану (отход через ~2 ч)
        poti = build_plan(
            "MC-26-0365",
            "TransCaspian Logistics",
            "1 × 40' reefer, продукты питания",
            ROUTE_KURYK,
            EventKind.arrived,
            "POTI",
            now - 10 * h,
        )

        # 6. Чёрное море: ро-ро, которого нет в нашем AIS-списке — только проекция
        black_sea = build_plan(
            "MC-26-0351",
            "Danube Cargo SRL",
            "4 × 40' HC, бытовая техника",
            ROUTE_BATUMI,
            EventKind.departed,
            "BATUMI",
            now - 30 * h,
            vessels={("BATUMI", "CONSTANTA"): "Black Sea Link"},
        )

        # 7. Доставлен в Будапешт
        delivered = build_plan(
            "MC-26-0322",
            "EuroAsia Rail",
            "1 × 40' HC, текстиль",
            ROUTE_KURYK,
            EventKind.arrived,
            "BUDAPEST",
            now - 30 * h,
        )

        # 8. Только что покинул Хоргос после перегруза на широкую колею
        khorgos = build_plan(
            "MC-26-0447",
            "Tianshan Trade",
            "2 × 40' HC, станки",
            ROUTE_KURYK,
            EventKind.departed,
            "KHORGOS",
            now - 2 * h,
            delay_hours=6.0,
            pivot_note="перегруз на колею 1520 завершён",
            pivot_note_code="gauge_change_done",
        )

        # 9. Ещё в Китае: Сиань → Урумчи
        china = build_plan(
            "MC-26-0455",
            "Silk Road Forwarders",
            "3 × 40' HC, аккумуляторы",
            ROUTE_KURYK,
            EventKind.departed,
            "XIAN",
            now - 20 * h,
        )

        # 10. Привязан к парому «Azerbaijan» вне AIS: в море — проекция,
        #     в порту — ждёт погрузки/возвращения парома
        az = ferries["Azerbaijan"]
        if az.sailing and az.westbound:
            no_ais = build_plan(
                "MC-26-0405",
                "Steppe Freight KZ",
                "2 × 20', ферросплавы",
                ROUTE_AKTAU,
                EventKind.departed,
                "AKTAU",
                az.sail_start,
                vessels={("AKTAU", "BAKU_ALAT"): az.spec.name},
            )
        else:
            reason = (
                "Ожидание погрузки на паром «Azerbaijan»"
                if az.westbound
                else "Ожидание парома «Azerbaijan» с обратного рейса"
            )
            no_ais = build_plan(
                "MC-26-0405",
                "Steppe Freight KZ",
                "2 × 20', ферросплавы",
                ROUTE_AKTAU,
                EventKind.arrived,
                "AKTAU",
                min(now - 14 * h, az.sail_start - 14 * h),
                vessels={("AKTAU", "BAKU_ALAT"): az.spec.name},
                hold_reason=reason,
                hold_code="ferry_loading_wait" if az.westbound else "ferry_return_wait",
                hold_vessel=az.spec.name,
            )

        return [
            on_ferry,
            weather_hold,
            steppe,
            customs,
            poti,
            black_sea,
            delivered,
            khorgos,
            china,
            no_ais,
        ]
