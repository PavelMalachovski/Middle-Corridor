"""Справочник геометрии коридора: узлы и сегменты маршрута.

Порты в проде живут в БД (сиды миграции), но ломаные рельсов и морских
переправ между узлами — статическая справочная геометрия: по ней рисуется
маршрут на карте и интерполируется положение груза между чекпоинтами.
Координаты приблизительные (уровень «карта коридора», не навигация).
"""

import enum
from dataclasses import dataclass, replace

from app.db.models import CorridorLeg
from app.services.geo import LatLon, polyline_length_km


class NodeKind(enum.StrEnum):
    port = "port"
    rail = "rail"
    border = "border"


class TransportMode(enum.StrEnum):
    rail = "rail"
    sea = "sea"


@dataclass(frozen=True, slots=True)
class CorridorNode:
    code: str
    name: str
    country: str
    leg: CorridorLeg
    lat: float
    lon: float
    kind: NodeKind
    name_en: str = ""  # для интерфейса на английском; заполняется из _EN ниже
    country_en: str = ""

    @property
    def latlon(self) -> LatLon:
        return (self.lat, self.lon)


@dataclass(frozen=True, slots=True)
class CorridorSegment:
    from_code: str
    to_code: str
    mode: TransportMode
    points: tuple[LatLon, ...]  # включая оба конца
    typical_hours: float  # типичное время в пути (для мок-расписаний)

    @property
    def length_km(self) -> float:
        return polyline_length_km(self.points)


_N = CorridorNode
_L = CorridorLeg

NODES: dict[str, CorridorNode] = {
    n.code: n
    for n in [
        # Китай — точки отправления
        _N("XIAN", "Сиань", "Китай", _L.rail_cis, 34.34, 108.94, NodeKind.rail),
        _N("URUMQI", "Урумчи", "Китай", _L.rail_cis, 43.83, 87.62, NodeKind.rail),
        # Казахстан
        _N(
            "KHORGOS", "Хоргос / Алтынколь", "Казахстан", _L.rail_cis, 44.19, 80.10, NodeKind.border
        ),
        _N("ALMATY", "Алматы", "Казахстан", _L.rail_cis, 43.24, 76.95, NodeKind.rail),
        _N("SHYMKENT", "Шымкент", "Казахстан", _L.rail_cis, 42.32, 69.60, NodeKind.rail),
        _N("KYZYLORDA", "Кызылорда", "Казахстан", _L.rail_cis, 44.85, 65.51, NodeKind.rail),
        _N("BEINEU", "Бейнеу", "Казахстан", _L.rail_cis, 45.32, 55.19, NodeKind.rail),
        _N("AKTAU", "Актау", "Казахстан", _L.caspian, 43.63, 51.25, NodeKind.port),
        _N("KURYK", "Курык", "Казахстан", _L.caspian, 43.19, 51.65, NodeKind.port),
        # Азербайджан
        _N("BAKU_ALAT", "Баку (Алят)", "Азербайджан", _L.caspian, 39.93, 49.41, NodeKind.port),
        _N("GANJA", "Гянджа", "Азербайджан", _L.rail_caucasus, 40.68, 46.36, NodeKind.rail),
        _N(
            "BOYUK_KASIK",
            "Бёюк-Кясик / Гардабани",
            "Азербайджан",
            _L.rail_caucasus,
            41.44,
            45.10,
            NodeKind.border,
        ),
        # Грузия
        _N("TBILISI", "Тбилиси", "Грузия", _L.rail_caucasus, 41.72, 44.80, NodeKind.rail),
        _N("POTI", "Поти", "Грузия", _L.black_sea, 42.15, 41.65, NodeKind.port),
        _N("BATUMI", "Батуми", "Грузия", _L.black_sea, 41.65, 41.64, NodeKind.port),
        # Европа
        _N("CONSTANTA", "Констанца", "Румыния", _L.europe, 44.17, 28.65, NodeKind.port),
        _N("BUCHAREST", "Бухарест", "Румыния", _L.europe, 44.43, 26.10, NodeKind.rail),
        _N("BUDAPEST", "Будапешт", "Венгрия", _L.europe, 47.50, 19.05, NodeKind.rail),
    ]
}

# Английские названия узлов для интерфейса. Транслитерация по общепринятым формам
# (Kuryk, Alat, Böyük Kəsik); термины коридора стоит вычитать с человеком из отрасли.
_EN: dict[str, tuple[str, str]] = {
    "XIAN": ("Xi'an", "China"),
    "URUMQI": ("Ürümqi", "China"),
    "KHORGOS": ("Khorgos / Altynkol", "Kazakhstan"),
    "ALMATY": ("Almaty", "Kazakhstan"),
    "SHYMKENT": ("Shymkent", "Kazakhstan"),
    "KYZYLORDA": ("Kyzylorda", "Kazakhstan"),
    "BEINEU": ("Beyneu", "Kazakhstan"),
    "AKTAU": ("Aktau", "Kazakhstan"),
    "KURYK": ("Kuryk", "Kazakhstan"),
    "BAKU_ALAT": ("Baku (Alat)", "Azerbaijan"),
    "GANJA": ("Ganja", "Azerbaijan"),
    "BOYUK_KASIK": ("Böyük Kəsik / Gardabani", "Azerbaijan"),
    "TBILISI": ("Tbilisi", "Georgia"),
    "POTI": ("Poti", "Georgia"),
    "BATUMI": ("Batumi", "Georgia"),
    "CONSTANTA": ("Constanța", "Romania"),
    "BUCHAREST": ("Bucharest", "Romania"),
    "BUDAPEST": ("Budapest", "Hungary"),
}
NODES = {
    code: replace(node, name_en=_EN[code][0], country_en=_EN[code][1])
    for code, node in NODES.items()
}


def _seg(a: str, b: str, mode: TransportMode, hours: float, *via: LatLon) -> CorridorSegment:
    points = (NODES[a].latlon, *via, NODES[b].latlon)
    return CorridorSegment(a, b, mode, points, hours)


_R = TransportMode.rail
_S = TransportMode.sea

SEGMENTS: dict[tuple[str, str], CorridorSegment] = {
    (s.from_code, s.to_code): s
    for s in [
        _seg("XIAN", "URUMQI", _R, 60, (36.06, 103.83), (39.75, 98.5), (42.83, 93.5)),
        _seg("URUMQI", "KHORGOS", _R, 14, (44.6, 82.9)),
        _seg("KHORGOS", "ALMATY", _R, 12, (44.15, 79.0)),
        _seg("ALMATY", "SHYMKENT", _R, 14, (43.6, 73.75), (42.9, 71.4)),
        _seg("SHYMKENT", "KYZYLORDA", _R, 12, (43.3, 68.25)),
        _seg("KYZYLORDA", "BEINEU", _R, 26, (46.78, 61.66), (46.3, 58.0)),
        _seg("BEINEU", "AKTAU", _R, 10, (44.17, 52.1)),
        _seg("BEINEU", "KURYK", _R, 12, (44.17, 52.1), (43.55, 51.9)),
        # Переправа через Каспий — огибаем Апшеронский полуостров с востока
        _seg(
            "KURYK",
            "BAKU_ALAT",
            _S,
            20,
            (42.3, 51.4),
            (41.0, 51.1),
            (40.45, 50.9),
            (40.05, 50.1),
        ),
        _seg(
            "AKTAU",
            "BAKU_ALAT",
            _S,
            22,
            (42.8, 51.2),
            (41.0, 51.1),
            (40.45, 50.9),
            (40.05, 50.1),
        ),
        _seg("BAKU_ALAT", "GANJA", _R, 8, (40.34, 48.15), (40.62, 47.15)),
        _seg("GANJA", "BOYUK_KASIK", _R, 5, (40.99, 45.63)),
        _seg("BOYUK_KASIK", "TBILISI", _R, 3, (41.46, 45.09)),
        _seg(
            "TBILISI",
            "POTI",
            _R,
            10,
            (41.98, 44.11),
            (41.99, 43.6),
            (42.11, 43.05),
            (42.16, 42.34),
        ),
        _seg(
            "TBILISI",
            "BATUMI",
            _R,
            11,
            (41.98, 44.11),
            (41.99, 43.6),
            (42.11, 43.05),
            (42.16, 42.34),
            (41.9, 41.8),
        ),
        _seg("POTI", "CONSTANTA", _S, 48, (43.2, 38.0), (43.6, 33.0)),
        _seg("BATUMI", "CONSTANTA", _S, 50, (42.9, 38.0), (43.6, 33.0)),
        _seg("CONSTANTA", "BUCHAREST", _R, 6),
        _seg("BUCHAREST", "BUDAPEST", _R, 24, (45.66, 25.6), (46.77, 23.6), (47.07, 21.93)),
    ]
}


def segment(a: str, b: str) -> CorridorSegment:
    """Сегмент между узлами в любом направлении (обратный — перевёрнутая ломаная)."""
    if (a, b) in SEGMENTS:
        return SEGMENTS[(a, b)]
    if (b, a) in SEGMENTS:
        fwd = SEGMENTS[(b, a)]
        return CorridorSegment(a, b, fwd.mode, tuple(reversed(fwd.points)), fwd.typical_hours)
    raise KeyError(f"нет сегмента {a} → {b}")


def route_points(codes: list[str]) -> list[LatLon]:
    """Сшивает сегменты маршрута в одну ломаную без дублирования стыков."""
    points: list[LatLon] = []
    for a, b in zip(codes, codes[1:], strict=False):
        seg_points = segment(a, b).points
        points.extend(seg_points if not points else seg_points[1:])
    return points
