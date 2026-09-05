"""Трекинг отправок: план маршрута, подтверждённые события, проекция положения.

Честная модель для коридора, где сплошного GPS/AIS нет: положение груза —
это последнее ПОДТВЕРЖДЁННОЕ событие (отправление/прибытие в узле, AIS-позиция
парома) плюс ПРОЕКЦИЯ по расписанию между чекпоинтами. Фронт рисует их
по-разному: подтверждённая точка — сплошная, проекция — пунктир/пульс.

Источник планов и событий — Protocol ShipmentSource (мок в прототипе,
позже — интеграции с экспедиторами/операторами).
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel

from app.services.corridor import NODES, TransportMode, route_points, segment
from app.services.geo import LatLon, point_along, polyline_length_km


class EventKind(enum.StrEnum):
    departed = "departed"
    arrived = "arrived"


class ShipmentState(enum.StrEnum):
    planned = "planned"
    in_transit = "in_transit"
    waiting = "waiting"
    delivered = "delivered"


class CheckpointState(enum.StrEnum):
    done = "done"
    current = "current"
    planned = "planned"


class PositionSource(enum.StrEnum):
    event = "event"  # стоим в узле — подтверждено событием
    ais = "ais"  # на пароме с живой AIS-позицией
    projection = "projection"  # оценка по расписанию


@dataclass(frozen=True, slots=True)
class PlannedLeg:
    from_code: str
    to_code: str
    depart_at: datetime
    arrive_at: datetime
    vessel: str | None = None  # имя судна на морском плече


@dataclass(frozen=True, slots=True)
class TrackingEvent:
    kind: EventKind
    node_code: str
    ts: datetime
    note: str | None = None  # текст для бота/RU
    note_code: str | None = None  # код для интерфейса: loaded_on_vessel, gauge_change_done…
    note_vessel: str | None = None  # параметр кода: имя судна


@dataclass(frozen=True, slots=True)
class ShipmentPlan:
    ref: str
    client: str
    cargo: str
    legs: tuple[PlannedLeg, ...]
    events: tuple[TrackingEvent, ...]  # отсортированы по ts
    hold_reason: str | None = None  # почему стоим дольше плана (текст, RU)
    hold_code: str | None = None  # код причины: weather_ban, customs_wait, ferry_*_wait
    hold_node: str | None = None  # узел причины (порт, граница)
    hold_vessel: str | None = None  # судно причины
    cargo_en: str | None = None  # описание груза по-английски (для карты в EN)

    @property
    def route(self) -> list[str]:
        return [self.legs[0].from_code, *(leg.to_code for leg in self.legs)]


class Checkpoint(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    planned_at: datetime
    actual_at: datetime | None = None
    state: CheckpointState


class ShipmentPosition(BaseModel):
    lat: float
    lon: float
    heading: float | None = None
    confirmed: bool
    source: PositionSource
    on_vessel: str | None = None
    mode: TransportMode | None = None  # None = стоим в узле
    from_code: str
    to_code: str | None = None
    leg_progress: float = 0.0  # 0..1 по текущему плечу


class Shipment(BaseModel):
    ref: str
    client: str
    cargo: str
    cargo_en: str | None = None
    origin: str
    destination: str
    origin_code: str = ""
    destination_code: str = ""
    state: ShipmentState
    hold_reason: str | None = None
    hold_code: str | None = None
    hold_node: str | None = None
    hold_vessel: str | None = None
    delay_hours: float = 0.0
    last_event: str
    last_event_kind: EventKind | None = None
    last_event_node: str | None = None
    last_event_note_code: str | None = None
    last_event_note_vessel: str | None = None
    last_event_at: datetime | None = None
    eta: datetime | None = None
    position: ShipmentPosition
    progress: float  # 0..1 по длине маршрута
    checkpoints: list[Checkpoint]
    track: list[list[float]]  # [lon, lat] — порядок GeoJSON


class ShipmentSource(Protocol):
    async def list_plans(self, at: datetime | None = None) -> list[ShipmentPlan]:
        """Планы и события, известные на момент at (None = сейчас)."""
        ...


def _hours(delta: timedelta) -> float:
    return max(delta.total_seconds() / 3600.0, 0.0)


def _event_label(event: TrackingEvent) -> str:
    verb = "Отправление" if event.kind == EventKind.departed else "Прибытие"
    label = f"{verb}: {NODES[event.node_code].name}"
    return f"{label} — {event.note}" if event.note else label


def project_shipment(  # noqa: PLR0912, PLR0915 — линейный разбор состояний
    plan: ShipmentPlan,
    now: datetime,
    vessel_positions: Mapping[str, LatLon] | None = None,
) -> Shipment:
    """Состояние отправки на момент now по плану и подтверждённым событиям."""
    vessel_positions = vessel_positions or {}
    route = plan.route
    legs_by_from = {leg.from_code: leg for leg in plan.legs}
    legs_by_to = {leg.to_code: leg for leg in plan.legs}
    past = [event for event in plan.events if event.ts <= now]
    last = past[-1] if past else None

    delay_hours = 0.0
    done_km = 0.0
    state = ShipmentState.planned
    position: ShipmentPosition

    if last is None:
        origin = NODES[route[0]]
        position = ShipmentPosition(
            lat=origin.lat,
            lon=origin.lon,
            confirmed=True,
            source=PositionSource.event,
            from_code=route[0],
            to_code=route[1] if len(route) > 1 else None,
        )
        current_code = route[0]
    elif last.kind == EventKind.departed:
        leg = legs_by_from[last.node_code]
        seg = segment(leg.from_code, leg.to_code)
        planned_duration = leg.arrive_at - leg.depart_at
        arrive_est = last.ts + planned_duration
        fraction = _hours(now - last.ts) / max(_hours(planned_duration), 1e-6)
        fraction = min(fraction, 0.98)  # опоздание: держим у узла, но не «прибыли»
        delay_hours = max(_hours(last.ts - leg.depart_at), _hours(now - arrive_est))
        vessel_pos = vessel_positions.get(leg.vessel) if leg.vessel else None
        if vessel_pos is not None:
            (lat, lon), heading = vessel_pos, point_along(seg.points, fraction)[1]
            source, confirmed = PositionSource.ais, True
        else:
            (lat, lon), heading = point_along(seg.points, fraction)
            source, confirmed = PositionSource.projection, False
        position = ShipmentPosition(
            lat=lat,
            lon=lon,
            heading=heading,
            confirmed=confirmed,
            source=source,
            on_vessel=leg.vessel,
            mode=seg.mode,
            from_code=leg.from_code,
            to_code=leg.to_code,
            leg_progress=fraction,
        )
        done_km = _km_before(route, leg.from_code) + seg.length_km * fraction
        state = ShipmentState.in_transit
        current_code = leg.to_code
    else:  # arrived
        node = NODES[last.node_code]
        inbound = legs_by_to.get(last.node_code)
        if inbound is not None:
            delay_hours = _hours(last.ts - inbound.arrive_at)
        next_leg = legs_by_from.get(last.node_code)
        if next_leg is None:
            state = ShipmentState.delivered
        else:
            state = ShipmentState.waiting
            delay_hours = max(delay_hours, _hours(now - next_leg.depart_at))
        position = ShipmentPosition(
            lat=node.lat,
            lon=node.lon,
            confirmed=True,
            source=PositionSource.event,
            from_code=last.node_code,
            to_code=next_leg.to_code if next_leg else None,
        )
        done_km = _km_before(route, last.node_code)
        current_code = last.node_code

    total_km = polyline_length_km(route_points(route))
    progress = 1.0 if state == ShipmentState.delivered else min(done_km / total_km, 1.0)

    checkpoints = _checkpoints(plan, past, current_code, state)
    if state == ShipmentState.delivered:
        eta = last.ts if last else None
    else:
        eta = plan.legs[-1].arrive_at + timedelta(hours=delay_hours)

    return Shipment(
        ref=plan.ref,
        client=plan.client,
        cargo=plan.cargo,
        cargo_en=plan.cargo_en,
        origin=NODES[route[0]].name,
        destination=NODES[route[-1]].name,
        origin_code=route[0],
        destination_code=route[-1],
        state=state,
        hold_reason=plan.hold_reason if state == ShipmentState.waiting else None,
        hold_code=plan.hold_code if state == ShipmentState.waiting else None,
        hold_node=plan.hold_node if state == ShipmentState.waiting else None,
        hold_vessel=plan.hold_vessel if state == ShipmentState.waiting else None,
        delay_hours=round(delay_hours, 1),
        last_event=_event_label(last) if last else "Ожидает отправления",
        last_event_kind=last.kind if last else None,
        last_event_node=last.node_code if last else None,
        last_event_note_code=last.note_code if last else None,
        last_event_note_vessel=last.note_vessel if last else None,
        last_event_at=last.ts if last else None,
        eta=eta,
        position=position,
        progress=round(progress, 4),
        checkpoints=checkpoints,
        track=[[lon, lat] for lat, lon in route_points(route)],
    )


def _km_before(route: list[str], code: str) -> float:
    """Длина маршрута от начала до узла code."""
    idx = route.index(code)
    return sum(
        segment(a, b).length_km for a, b in zip(route[:idx], route[1 : idx + 1], strict=False)
    )


def _checkpoints(
    plan: ShipmentPlan,
    past: list[TrackingEvent],
    current_code: str,
    state: ShipmentState,
) -> list[Checkpoint]:
    route = plan.route
    arrivals = {e.node_code: e.ts for e in past if e.kind == EventKind.arrived}
    departures = {e.node_code: e.ts for e in past if e.kind == EventKind.departed}
    result: list[Checkpoint] = []
    for idx, code in enumerate(route):
        node = NODES[code]
        planned_at = plan.legs[0].depart_at if idx == 0 else plan.legs[idx - 1].arrive_at
        actual_at = departures.get(code) if idx == 0 else arrivals.get(code)
        if code == current_code and state != ShipmentState.delivered:
            cp_state = CheckpointState.current
        elif actual_at is not None:
            cp_state = CheckpointState.done
        else:
            cp_state = CheckpointState.planned
        result.append(
            Checkpoint(
                code=code,
                name=node.name,
                lat=node.lat,
                lon=node.lon,
                planned_at=planned_at,
                actual_at=actual_at,
                state=cp_state,
            )
        )
    return result
