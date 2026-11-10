import Foundation

// Логика форм аккаунта (новый груз, правка, «Отметить событие», люди) без UI — чтобы её
// проверял `swift test`. Сервер всё равно проверяет всё сам; здесь — чтобы форма не давала
// отправить заведомый отказ и объясняла его словами.

/// Кто что может в интерфейсе — по `Me.memberships` (права на сервере — `access.py`).
public enum AccountAccess {
    private static func manages(_ m: MembershipInfo) -> Bool {
        m.role.known == .owner || m.role.known == .admin
    }

    /// Компании, где можно создать груз: экспедитор, роль owner/admin (платформа-админ — любой экспедитор).
    public static func creatableOrgs(_ me: Me?) -> [MembershipInfo] {
        guard let me else { return [] }
        return me.memberships.filter { m in
            m.orgKind.known == .forwarder && (me.isPlatformAdmin || manages(m))
        }
    }

    /// Компании, где можно смотреть команду и приглашать людей.
    public static func managedOrgs(_ me: Me?) -> [MembershipInfo] {
        guard let me else { return [] }
        return me.memberships.filter { me.isPlatformAdmin || manages($0) }
    }

    public static func canManageMembers(_ me: Me?, orgId: Int) -> Bool {
        managedOrgs(me).contains { $0.orgId == orgId }
    }
}

/// Готовые маршруты — те же списки узлов, что у мока (`app/integrations/mock/fleet.py`).
public enum RoutePreset: String, CaseIterable, Sendable, Identifiable {
    /// `ROUTE_KOSTANAY`: завод → Копер → Амбарлы → Поти → … → Актау → Костанай.
    case europeToKazakhstan
    /// `ROUTE_AKTAU`: Сиань → … → Актау → Баку → … → Поти → Констанца.
    case chinaToEurope

    public var id: String { rawValue }

    public var codes: [String] {
        switch self {
        case .europeToKazakhstan:
            [
                "MLADA_BOLESLAV", "KOPER", "AMBARLI", "POTI", "TBILISI", "BOYUK_KASIK", "GANJA",
                "BAKU_ALAT", "AKTAU", "BEINEU", "KOSTANAY",
            ]
        case .chinaToEurope:
            [
                "XIAN", "URUMQI", "KHORGOS", "ALMATY", "SHYMKENT", "KYZYLORDA", "BEINEU", "AKTAU",
                "BAKU_ALAT", "GANJA", "BOYUK_KASIK", "TBILISI", "POTI", "CONSTANTA",
            ]
        }
    }
}

/// Плечи коридора из снимка (`MapSnapshot.segments`): в обе стороны, как `corridor.segment`.
public struct RouteGraph: Sendable {
    private let modes: [String: TransportMode]
    private let neighbours: [String: Set<String>]
    /// Все узлы, у которых есть плечи, по коду.
    public let nodes: [String]

    public init(segments: [RouteSegment]) {
        var modes: [String: TransportMode] = [:]
        var neighbours: [String: Set<String>] = [:]
        for s in segments {
            let mode = s.mode.known ?? .rail
            modes[Self.pair(s.fromCode, s.toCode)] = mode
            neighbours[s.fromCode, default: []].insert(s.toCode)
            neighbours[s.toCode, default: []].insert(s.fromCode)
        }
        self.modes = modes
        self.neighbours = neighbours
        nodes = neighbours.keys.sorted()
    }

    private static func pair(_ a: String, _ b: String) -> String { a < b ? "\(a)|\(b)" : "\(b)|\(a)" }

    /// Вид плеча между соседними узлами; не плечо — nil.
    public func mode(_ a: String, _ b: String) -> TransportMode? { modes[Self.pair(a, b)] }

    /// Чем можно продолжить маршрут: пусто — любой узел; иначе соседи последнего, ещё не взятые.
    public func nextChoices(after route: [String]) -> [String] {
        guard let last = route.last else { return nodes }
        return (neighbours[last] ?? []).subtracting(route).sorted()
    }

    /// ≥2 узлов, без повторов, каждая пара — плечо (как `validate_route` сервера).
    public func isValid(_ route: [String]) -> Bool {
        guard route.count >= 2, Set(route).count == route.count else { return false }
        return zip(route, route.dropFirst()).allSatisfy { mode($0, $1) != nil }
    }

    /// Следующее плечо маршрута из этого узла — морское (тогда в событии есть поле «судно»).
    public func nextLegIsSea(from node: String, route: [String]) -> Bool {
        guard let i = route.firstIndex(of: node), i + 1 < route.count else { return false }
        return mode(route[i], route[i + 1]) == .sea
    }
}

/// Правка маршрута: пройденная часть не меняется (сервер: `route_passed_part`).
public enum RouteEdit {
    public static func route(_ s: Shipment) -> [String] { s.checkpoints.map(\.code) }

    /// Сколько первых узлов зафиксировано: до последнего, где груз уже был (done/current или факт).
    public static func lockedCount(_ s: Shipment) -> Int {
        let reached = s.checkpoints.lastIndex { c in
            c.actualAt != nil || c.state.known == .done || c.state.known == .current
        }
        return reached.map { $0 + 1 } ?? 0
    }
}

/// Черновик формы «Отметить событие».
public struct EventDraft: Sendable, Equatable {
    public static let noteMax = 500
    public static let vesselMax = 64

    public var kind: CheckpointKind = .arrived
    public var node: String
    /// Причина — только для `held`; не выбрана — отправлять нельзя.
    public var hold: HoldCode?
    public var note = ""
    public var vessel = ""
    /// nil — время не меняли: «сейчас» ставит сервер.
    public var occurredAt: Date?

    public init(node: String) { self.node = node }

    /// Узлы, где можно отметить событие: права (`eventNodes`) ∩ маршрут, в порядке маршрута.
    public static func nodeChoices(_ mine: MyShipment) -> [String] {
        let allowed = Set(mine.eventNodes)
        return RouteEdit.route(mine.shipment).filter { allowed.contains($0) }
    }

    private static func trimmed(_ s: String) -> String { s.trimmingCharacters(in: .whitespacesAndNewlines) }

    public var canSubmit: Bool {
        guard note.count <= Self.noteMax, Self.trimmed(vessel).count <= Self.vesselMax else { return false }
        guard kind == .held else { return true }
        guard let hold else { return false }
        // «другая причина» уходит с кодом "other"; её текст (обязателен) — примечание
        return hold != .other || !Self.trimmed(note).isEmpty
    }

    public func input(vesselAllowed: Bool) -> CheckpointEventInput {
        let note = Self.trimmed(note)
        let vessel = Self.trimmed(vessel)
        return CheckpointEventInput(
            kind: kind, nodeCode: node, occurredAt: occurredAt,
            holdCode: kind == .held ? hold?.rawValue : nil,
            note: note.isEmpty ? nil : note,
            vessel: vesselAllowed && !vessel.isEmpty ? vessel : nil)
    }
}

/// Ошибка API → ключ текста в Localizable.xcstrings (`account.error.<код>`).
public enum AccountErrorKey {
    static let known: Set<String> = [
        "node_not_allowed", "in_future", "out_of_order", "backwards", "hold_code_required", "bad_hold_code",
        "no_open_hold", "bad_supersedes", "note_too_long", "vessel_too_long", "archived", "bad_container",
        "bad_route", "route_passed_part", "unknown_node", "nodes_for_agent_only", "last_owner",
    ]

    public static func key(_ error: APIError) -> String {
        switch error {
        case .rejected(let code): known.contains(code) ? "account.error.\(code)" : "account.error.generic"
        case .offline: "settings.fail.offline"
        case .notFound: "account.error.notFound"
        case .unauthorized: "account.expired"
        case .http, .decoding: "account.error.generic"
        }
    }
}

/// Токен APNs для `POST /me/devices` — hex в нижнем регистре.
public enum PushToken {
    public static func hex(_ token: Data) -> String { token.map { String(format: "%02x", $0) }.joined() }
}
