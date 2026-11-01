import Foundation

/// Точка на карте (без CoreLocation — MCCore тестируется на macOS без UI-фреймворков).
public struct GeoPoint: Sendable, Hashable {
    public var lat: Double
    public var lon: Double

    public init(lat: Double, lon: Double) {
        self.lat = lat
        self.lon = lon
    }
}

/// Геометрия маршрута для карты в карточке груза.
public enum RouteGeometry {
    private static let vertexTolerance = 1e-6

    /// Делит трек (`[lon, lat]`) в точке положения на пройденное и оставшееся.
    /// Положение входит в обе части; совпадающая с ним вершина не дублируется.
    /// Доставлен — весь трек пройден.
    public static func split(
        track: [[Double]], at position: ShipmentPosition, state: ShipmentState?
    ) -> (done: [GeoPoint], rest: [GeoPoint]) {
        let points = track.compactMap { $0.count >= 2 ? GeoPoint(lat: $0[1], lon: $0[0]) : nil }
        guard !points.isEmpty else { return ([], []) }
        if state == .delivered { return (points, []) }

        let here = GeoPoint(lat: position.lat, lon: position.lon)
        if let vertex = points.firstIndex(where: {
            abs($0.lat - here.lat) < vertexTolerance && abs($0.lon - here.lon) < vertexTolerance
        }) {
            return (Array(points[...vertex]), Array(points[vertex...]))
        }
        guard points.count > 1 else { return ([points[0], here], [here]) }
        let nearest = (0..<(points.count - 1)).min {
            distance(here, points[$0], points[$0 + 1]) < distance(here, points[$1], points[$1 + 1])
        } ?? 0
        return (Array(points[...nearest]) + [here], [here] + Array(points[(nearest + 1)...]))
    }

    /// Порт для блока «Погода»: где груз стоит, а в пути — ближайший порт впереди по маршруту.
    public static func weatherPort(for s: Shipment, nodes: [NodeStatus]) -> NodeStatus? {
        let byCode = Dictionary(nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        if s.position.mode == nil, let here = byCode[s.position.fromCode], here.isWeatherTracked {
            return here
        }
        return s.checkpoints
            .filter { $0.state.known != .done }
            .lazy
            .compactMap { byCode[$0.code] }
            .first { $0.isWeatherTracked }
    }

    /// Расстояние от точки до отрезка в плоской проекции (долгота сжата на cos широты).
    private static func distance(_ p: GeoPoint, _ a: GeoPoint, _ b: GeoPoint) -> Double {
        let k = cos(p.lat * .pi / 180)
        let (px, py) = (p.lon * k, p.lat)
        let (ax, ay) = (a.lon * k, a.lat)
        let (bx, by) = (b.lon * k, b.lat)
        let (dx, dy) = (bx - ax, by - ay)
        let len2 = dx * dx + dy * dy
        let t = len2 == 0 ? 0 : max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / len2))
        let (cx, cy) = (ax + t * dx, ay + t * dy)
        return (px - cx) * (px - cx) + (py - cy) * (py - cy)
    }
}
