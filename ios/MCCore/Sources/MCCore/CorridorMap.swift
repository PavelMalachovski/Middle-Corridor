import Foundation

/// Итог точности по коридору: сумма по портам, медиана заблаговременности портов с данными.
public struct AccuracySummary: Sendable, Equatable {
    public var closures: Int
    public var hits: Int
    public var alerts: Int
    public var falseAlarms: Int
    public var medianLeadH: Double?

    public init(closures: Int, hits: Int, alerts: Int, falseAlarms: Int, medianLeadH: Double?) {
        self.closures = closures
        self.hits = hits
        self.alerts = alerts
        self.falseAlarms = falseAlarms
        self.medianLeadH = medianLeadH
    }

    public static func make(_ report: AccuracyReport) -> AccuracySummary {
        let leads = report.ports.compactMap(\.medianLeadH).sorted()
        let median: Double? =
            leads.isEmpty
            ? nil
            : leads.count % 2 == 1
                ? leads[leads.count / 2] : (leads[leads.count / 2 - 1] + leads[leads.count / 2]) / 2
        return AccuracySummary(
            closures: report.ports.map(\.closures).reduce(0, +),
            hits: report.ports.map(\.hits).reduce(0, +),
            alerts: report.ports.map(\.alerts).reduce(0, +),
            falseAlarms: report.ports.map(\.falseAlarms).reduce(0, +),
            medianLeadH: median)
    }
}

/// Мой груз на карте коридора: положение и подтверждено ли оно (проекция рисуется контуром).
public struct MapShipment: Sendable, Hashable, Identifiable {
    public var id: String { ref }
    public let ref: String
    public let point: GeoPoint
    public let confirmed: Bool
    public let tone: StatusTone
}

/// Что рисовать на карте коридора.
public enum CorridorMap {
    /// Мои грузы для живой карты: доставленные не рисуем (их нет «в пути»), проекция — не факт.
    public static func shipments(_ list: [Shipment]) -> [MapShipment] {
        list.filter { $0.state.known != .delivered }.map {
            MapShipment(
                ref: $0.ref, point: GeoPoint(lat: $0.position.lat, lon: $0.position.lon),
                confirmed: $0.position.confirmed, tone: $0.tone)
        }
    }

    /// Паром движется: у причала стрелка курса вводила бы в заблуждение.
    public static func isMoving(_ vessel: VesselStatus) -> Bool {
        (vessel.sog ?? 0) >= 1 && vessel.cog != nil
    }

    /// Паромы с живой позицией: без AIS судна на карте нет («нет данных», а не «стоит»).
    public static func liveVessels(_ vessels: [VesselStatus]) -> [VesselStatus] {
        vessels.filter { $0.hasRecentData && $0.lat != nil && $0.lon != nil }
    }
}
