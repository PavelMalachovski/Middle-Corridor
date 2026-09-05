"""Справочник геометрии коридора: узлы и сегменты маршрута.

Порты в проде живут в БД (сиды миграции), но ломаные рельсов и морских
переправ между узлами — статическая справочная геометрия: по ней рисуется
маршрут на карте и интерполируется положение груза между чекпоинтами.
Координаты приблизительные (уровень «карта коридора», не навигация).
"""

import enum
import math
from dataclasses import dataclass, replace

from app.db.models import CorridorLeg
from app.services.geo import LatLon, point_in_polygon, polyline_length_km


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


# --- моря ------------------------------------------------------------------------
# Ветер важен там, где он что-то останавливает: паромы и порты Каспия и
# Чёрного моря. Над степью и горами поле ветра — шум. Полигоны (lat, lon)
# по береговой линии, грубо (±20 км): Каспий без Кара-Богаз-Гола, Чёрное
# море без Азова. Порядок обхода — по часовой стрелке от северо-запада.
SEAS: dict[str, tuple[LatLon, ...]] = {
    "caspian": (
        (46.3, 47.3),
        (46.9, 48.0),
        (46.9, 49.4),
        (46.7, 50.6),
        (46.5, 51.5),
        (46.0, 52.2),
        (45.4, 52.0),
        (44.9, 51.0),
        (44.5, 50.3),
        (44.0, 50.8),
        (43.65, 51.17),
        (43.2, 51.32),
        (42.7, 52.6),
        (42.1, 52.8),
        (41.5, 52.6),
        (40.6, 52.9),
        (40.0, 53.0),
        (39.4, 53.1),
        (38.6, 53.9),
        (37.5, 53.9),
        (36.9, 53.4),
        (36.7, 52.2),
        (36.8, 51.0),
        (37.4, 49.7),
        (38.0, 49.0),
        (38.8, 48.9),
        (39.4, 49.2),
        (39.95, 49.4),
        (40.18, 49.45),
        (40.3, 49.8),
        (40.32, 50.1),
        (40.4, 50.4),
        (40.6, 50.0),
        (40.65, 49.7),
        (41.3, 49.4),
        (41.9, 48.6),
        (42.6, 47.9),
        (43.2, 47.6),
        (44.0, 47.4),
        (44.6, 47.0),
        (45.3, 47.1),
        (45.9, 47.4),
    ),
    "black_sea": (
        (45.2, 29.75),
        (45.8, 30.0),
        (46.3, 30.8),
        (46.6, 31.5),
        (46.5, 32.3),
        (46.0, 32.8),
        (45.5, 32.8),
        (45.3, 32.5),
        (44.6, 33.4),
        (44.4, 33.8),
        (44.5, 34.4),
        (44.9, 35.3),
        (45.2, 36.0),
        (45.0, 36.5),
        (44.9, 37.3),
        (44.7, 37.7),
        (44.4, 38.4),
        (44.1, 39.0),
        (43.7, 39.6),
        (43.4, 40.0),
        (43.0, 40.9),
        (42.7, 41.5),
        (42.2, 41.6),
        (41.7, 41.6),
        (41.4, 41.3),
        (41.1, 40.3),
        (40.95, 39.7),
        (41.1, 38.5),
        (41.2, 37.4),
        (41.4, 36.3),
        (41.7, 35.5),
        (42.0, 35.0),
        (41.8, 34.0),
        (41.7, 32.8),
        (41.5, 31.8),
        (41.3, 30.5),
        (41.2, 29.2),
        (41.5, 28.4),
        (42.0, 28.0),
        (42.5, 27.6),
        (43.0, 27.9),
        (43.5, 28.4),
        (44.1, 28.7),
        (44.7, 29.0),
        (45.0, 29.6),
    ),
}

# lat_min, lon_min, lat_max, lon_max — общий охват морей; сетка ветра живёт в нём
SEA_BBOX: tuple[float, float, float, float] = (36.5, 27.5, 47.0, 54.0)


# Прибрежная полоса тоже «море»: порты и рейды стоят на самой линии грубого
# полигона, а ветер у берега — то, ради чего слой и нужен.
COAST_TOLERANCE_DEG = 0.2


def sea_at(lat: float, lon: float, tolerance_deg: float = 0.0) -> str | None:
    """Код моря под точкой или None над сушей.

    tolerance_deg > 0 — точка считается морской, если море есть в пределах
    ±tolerance по широте или долготе (прибрежная полоса).
    """
    probes = [(lat, lon)]
    if tolerance_deg > 0:
        probes += [
            (lat + tolerance_deg, lon),
            (lat - tolerance_deg, lon),
            (lat, lon + tolerance_deg),
            (lat, lon - tolerance_deg),
        ]
    for code, polygon in SEAS.items():
        if any(point_in_polygon(probe, polygon) for probe in probes):
            return code
    return None


def sea_grid(step_deg: float, bbox: tuple[float, float, float, float] = SEA_BBOX) -> list[LatLon]:
    """Узлы регулярной сетки с шагом step_deg, лежащие над морем.

    Узлы выровнены по кратным шага (не по краю bbox), чтобы сетки мока и
    боевого источника совпадали при любом bbox. Порядок — по широте, затем
    по долготе, как ждёт текстура ветра на фронте.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    lat0 = math.ceil(lat_min / step_deg - 1e-9) * step_deg
    lon0 = math.ceil(lon_min / step_deg - 1e-9) * step_deg
    points: list[LatLon] = []
    lat = lat0
    while lat <= lat_max + 1e-9:
        lon = lon0
        while lon <= lon_max + 1e-9:
            if sea_at(lat, lon, COAST_TOLERANCE_DEG) is not None:
                points.append((round(lat, 4), round(lon, 4)))
            lon += step_deg
        lat += step_deg
    return points


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
