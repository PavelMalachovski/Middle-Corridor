"""Геометрия на сфере: расстояния, азимуты, интерполяция вдоль ломаной.

Координаты везде — (lat, lon) в градусах; в GeoJSON порядок обратный
([lon, lat]) — конвертируется на границе API, не здесь.
"""

import math
from collections.abc import Sequence

EARTH_RADIUS_KM = 6371.0

LatLon = tuple[float, float]


def haversine_km(a: LatLon, b: LatLon) -> float:
    """Расстояние по дуге большого круга, км."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Начальный азимут из a в b, градусы по часовой от севера (0..360)."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d_lon = lon2 - lon1
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def polyline_length_km(points: Sequence[LatLon]) -> float:
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def point_along(points: Sequence[LatLon], fraction: float) -> tuple[LatLon, float]:
    """Точка на ломаной на доле fraction (0..1) её длины и курс в этой точке.

    Интерполяция линейная по сегментам — для отрисовки и оценки положения
    этого достаточно (сегменты короткие относительно радиуса Земли).
    """
    if not points:
        raise ValueError("пустая ломаная")
    if len(points) == 1:
        return points[0], 0.0
    fraction = min(max(fraction, 0.0), 1.0)
    total = polyline_length_km(points)
    if total == 0:
        return points[0], 0.0
    target = fraction * total
    walked = 0.0
    for i in range(len(points) - 1):
        seg = haversine_km(points[i], points[i + 1])
        if walked + seg >= target or i == len(points) - 2:
            t = (target - walked) / seg if seg > 0 else 0.0
            t = min(max(t, 0.0), 1.0)
            lat = points[i][0] + (points[i + 1][0] - points[i][0]) * t
            lon = points[i][1] + (points[i + 1][1] - points[i][1]) * t
            return (lat, lon), bearing_deg(points[i], points[i + 1])
        walked += seg
    return points[-1], bearing_deg(points[-2], points[-1])


def point_in_polygon(point: LatLon, polygon: Sequence[LatLon]) -> bool:
    """Лежит ли точка внутри многоугольника (лучевой метод, плоское приближение).

    Для морских полигонов масштаба сотен километров искажение проекции
    (lat, lon) как плоскости не важно: границы и так грубые.
    """
    lat, lon = point
    inside = False
    n = len(polygon)
    for i in range(n):
        lat_a, lon_a = polygon[i]
        lat_b, lon_b = polygon[(i + 1) % n]
        if (lat_a > lat) == (lat_b > lat):
            continue  # ребро не пересекает горизонталь через точку
        cross_lon = lon_a + (lat - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
        if lon < cross_lon:
            inside = not inside
    return inside
