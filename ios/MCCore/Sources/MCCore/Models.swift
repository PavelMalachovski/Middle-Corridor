import Foundation

// Модели /api/v1 — зеркало app/services/map_snapshot.py и app/services/tracking.py.
// Ключи snake_case переводит декодер (APIDate.makeDecoder); лишние ключи игнорируются.

/// Код из бэкенда: известное значение — `known`, неизвестное не роняет декод (`raw`).
public struct Coded<Known: RawRepresentable>: Codable, Sendable, Hashable
where Known.RawValue == String {
    public let raw: String
    public var known: Known? { Known(rawValue: raw) }

    public init(raw: String) { self.raw = raw }
    public init(_ known: Known) { self.raw = known.rawValue }

    public init(from decoder: Decoder) throws {
        raw = try decoder.singleValueContainer().decode(String.self)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(raw)
    }
}

public enum ShipmentState: String, Sendable, CaseIterable {
    case planned
    case inTransit = "in_transit"
    case waiting
    case delivered
}

public enum EventKind: String, Sendable { case departed, arrived }
public enum CheckpointState: String, Sendable { case done, current, planned }

/// event — стоим в узле (подтверждено), ais — на пароме с живой позицией,
/// projection — оценка по расписанию (НЕ факт).
public enum PositionSource: String, Sendable { case event, ais, projection }
public enum TransportMode: String, Sendable { case rail, sea }
public enum AlertLevel: String, Sendable, Comparable {
    case watch, warning, critical

    public static func < (a: AlertLevel, b: AlertLevel) -> Bool { a.rank < b.rank }
    private var rank: Int {
        switch self {
        case .watch: 0
        case .warning: 1
        case .critical: 2
        }
    }
}
public enum NodeKind: String, Sendable { case port, rail, border }

public struct ShipmentPosition: Codable, Sendable, Hashable {
    public var lat: Double
    public var lon: Double
    public var heading: Double?
    public var confirmed: Bool
    public var source: Coded<PositionSource>
    public var onVessel: String?
    public var mode: Coded<TransportMode>?
    public var fromCode: String
    public var toCode: String?
    public var legProgress: Double
}

public struct Checkpoint: Codable, Sendable, Hashable {
    public var code: String
    public var name: String
    public var lat: Double
    public var lon: Double
    public var plannedAt: Date
    public var actualAt: Date?
    public var state: Coded<CheckpointState>
}

public struct Shipment: Codable, Sendable, Hashable, Identifiable {
    public var id: String { ref }

    public var ref: String
    public var client: String
    public var cargo: String
    public var cargoEn: String?
    public var origin: String
    public var destination: String
    public var originCode: String
    public var destinationCode: String
    public var state: Coded<ShipmentState>
    public var holdReason: String?
    public var holdCode: String?
    public var holdNode: String?
    public var holdVessel: String?
    public var delayHours: Double
    public var lastEvent: String
    public var lastEventKind: Coded<EventKind>?
    public var lastEventNode: String?
    public var lastEventNoteCode: String?
    public var lastEventNoteVessel: String?
    public var lastEventAt: Date?
    public var eta: Date?
    public var position: ShipmentPosition
    public var progress: Double
    public var checkpoints: [Checkpoint]
    public var track: [[Double]]  // [lon, lat] — порядок GeoJSON
}

public struct NodeStatus: Codable, Sendable, Hashable, Identifiable {
    public var id: String { code }

    public var code: String
    public var name: String
    public var country: String
    public var nameEn: String?
    public var countryEn: String?
    public var kind: Coded<NodeKind>
    public var lat: Double
    public var lon: Double
    public var isWeatherTracked: Bool
    public var alertLevel: Coded<AlertLevel>?
    public var windSpeed: Double?
    public var windGust: Double?
    public var weatherTs: Date?
}

public struct NewsSummary: Codable, Sendable, Hashable, Identifiable {
    public var id: Int
    public var source: String
    public var title: String
    public var summary: String?
    public var url: String
    public var publishedAt: Date?
}

public struct WeekSummary: Codable, Sendable, Hashable {
    public var periodHours: Int
    public var caspianCrossings: Int
    public var avgDelayHours: Double?
    public var portDowntimeHours: Double?
    public var portsStopped: Int
}

public struct MapSnapshot: Codable, Sendable, Hashable {
    public var generatedAt: Date
    public var serverTime: Date
    public var replay: Bool
    public var mock: Bool
    public var nodes: [NodeStatus]
    public var shipments: [Shipment]
    public var news: [NewsSummary]
    public var summary: WeekSummary?
}
