import Foundation

/// Секция списка «Мои грузы»: сначала то, что требует внимания, доставленные — в конце.
public enum ShipmentGroup: Int, CaseIterable, Sendable, Comparable {
    /// Задержка, стоянка с причиной, риск остановки в порту на пути, «груз не найден».
    case attention
    /// В пути и ещё не загруженные строки.
    case active
    /// Ждёт отправления.
    case planned
    case delivered

    public static func < (a: ShipmentGroup, b: ShipmentGroup) -> Bool { a.rawValue < b.rawValue }

    /// Секция груза. `nodes` — снимок коридора: шторм в порту на пути поднимает груз наверх.
    public static func of(_ s: Shipment, nodes: [String: NodeStatus]) -> ShipmentGroup {
        switch s.state.known {
        case .delivered: return .delivered
        case .planned where !s.isDelayed && !hasStormAhead(s, nodes: nodes): return .planned
        default: break
        }
        if s.isDelayed || s.holdCode != nil || s.holdReason != nil || hasStormAhead(s, nodes: nodes) {
            return .attention
        }
        return s.state.known == .planned ? .planned : .active
    }

    /// Строки по секциям; внутри секции — порядок списка (последний добавленный — первым).
    /// Пустые секции не возвращаются.
    public static func group(
        _ rows: [TrackedRow], nodes: [NodeStatus], missing: Set<String> = []
    ) -> [ShipmentSection] {
        let byCode = Dictionary(nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        var buckets: [ShipmentGroup: [TrackedRow]] = [:]
        for row in rows {
            let group: ShipmentGroup
            if let shipment = row.shipment {
                group = of(shipment, nodes: byCode)
            } else {
                group = missing.contains(row.ref) ? .attention : .active
            }
            buckets[group, default: []].append(row)
        }
        return ShipmentGroup.allCases.compactMap { group in
            buckets[group].map { ShipmentSection(group: group, rows: $0) }
        }
    }

    /// Риск остановки (warning и выше) в порту, где груз стоит, или в порту впереди по маршруту.
    static func hasStormAhead(_ s: Shipment, nodes: [String: NodeStatus]) -> Bool {
        guard s.state.known != .delivered else { return false }
        var codes: [String] = s.position.mode == nil ? [s.position.fromCode] : []
        codes += s.checkpoints.filter { $0.state.known != .done }.map(\.code)
        return codes.contains { code in
            guard let node = nodes[code], node.isWeatherTracked, let level = node.alertLevel?.known else {
                return false
            }
            return level >= .warning
        }
    }
}

/// Секция списка с её строками.
public struct ShipmentSection: Identifiable, Sendable, Hashable {
    public var id: ShipmentGroup { group }
    public let group: ShipmentGroup
    public let rows: [TrackedRow]

    public init(group: ShipmentGroup, rows: [TrackedRow]) {
        self.group = group
        self.rows = rows
    }
}
