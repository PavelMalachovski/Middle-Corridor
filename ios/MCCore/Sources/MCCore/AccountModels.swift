import Foundation

// Модели API аккаунтов — зеркало app/api/routes/accounts_schemas.py.
// Даты разбирает APIDate (сервер отдаёт их и без пояса — это UTC); ключи — snake_case.

public enum OrgKind: String, Sendable { case forwarder, client, platform }
public enum AccountRole: String, Sendable { case owner, admin, agent, viewer }

/// Вид события на чекпоинте; `held`/`released` — стоянка начата/снята.
public enum CheckpointKind: String, Codable, Sendable, CaseIterable {
    case arrived, departed, held, released
}

/// Причины стоянки в форме; `other` уходит без кода — причина идёт текстом примечания.
public enum HoldCode: String, Sendable, CaseIterable {
    case weatherBan = "weather_ban"
    case customsWait = "customs_wait"
    case ferryLoadingWait = "ferry_loading_wait"
    case other

    /// Код для сервера: у `other` его нет.
    public var apiCode: String? { self == .other ? nil : rawValue }
}

public struct MembershipInfo: Codable, Sendable, Hashable {
    public let orgId: Int
    public let orgName: String
    public let orgKind: Coded<OrgKind>
    public let role: Coded<AccountRole>
    public let nodeCodes: [String]
}

public struct Me: Codable, Sendable, Hashable {
    public let id: Int
    public let email: String
    public let name: String?
    public let locale: String
    public let isPlatformAdmin: Bool
    public let memberships: [MembershipInfo]
}

/// Ответ `POST /auth/verify`.
public struct LoginResult: Codable, Sendable, Hashable, CustomStringConvertible,
    CustomDebugStringConvertible
{
    public let token: String
    public let me: Me

    // токен не должен попасть ни в лог, ни в отладчик
    public var description: String { "LoginResult(token: <redacted>, me: \(me.id))" }
    public var debugDescription: String { description }
}

/// Груз аккаунта: проекция + права на него. `eventNodes` — узлы маршрута, где можно
/// вносить события.
public struct MyShipment: Codable, Sendable, Hashable, Identifiable {
    public let shipment: Shipment
    public let orgId: Int
    public let canManage: Bool
    public let eventNodes: [String]
    public let containerNo: String?

    public var id: String { shipment.ref }
}

public struct NewShipment: Codable, Sendable, Equatable {
    public var orgId: Int
    public var containerNo: String
    public var containerType: String?
    public var route: [String]
    public var plannedDepartureAt: Date
    public var cargo: String?
    public var cargoEn: String?

    public init(
        orgId: Int, containerNo: String, containerType: String? = nil, route: [String],
        plannedDepartureAt: Date, cargo: String? = nil, cargoEn: String? = nil
    ) {
        self.orgId = orgId
        self.containerNo = containerNo
        self.containerType = containerType
        self.route = route
        self.plannedDepartureAt = plannedDepartureAt
        self.cargo = cargo
        self.cargoEn = cargoEn
    }
}

/// Правка груза: в тело попадают только заданные поля. Для очищаемых полей (тип, груз) —
/// `.some(nil)` отправляет `null` (очистить), `nil` — «не менять».
public struct ShipmentPatch: Encodable, Sendable, Equatable {
    public var containerNo: String?
    public var containerType: String??
    public var route: [String]?
    public var plannedDepartureAt: Date?
    public var cargo: String??
    public var cargoEn: String??

    public init(
        containerNo: String? = nil, containerType: String?? = nil, route: [String]? = nil,
        plannedDepartureAt: Date? = nil, cargo: String?? = nil, cargoEn: String?? = nil
    ) {
        self.containerNo = containerNo
        self.containerType = containerType
        self.route = route
        self.plannedDepartureAt = plannedDepartureAt
        self.cargo = cargo
        self.cargoEn = cargoEn
    }

    private enum CodingKeys: String, CodingKey {
        case containerNo, containerType, route, plannedDepartureAt, cargo, cargoEn
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(containerNo, forKey: .containerNo)
        if let containerType { try c.encode(containerType, forKey: .containerType) }
        try c.encodeIfPresent(route, forKey: .route)
        try c.encodeIfPresent(plannedDepartureAt, forKey: .plannedDepartureAt)
        if let cargo { try c.encode(cargo, forKey: .cargo) }
        if let cargoEn { try c.encode(cargoEn, forKey: .cargoEn) }
    }
}

public struct CheckpointEventInput: Codable, Sendable, Equatable {
    public var kind: CheckpointKind
    public var nodeCode: String
    /// nil — сервер ставит «сейчас».
    public var occurredAt: Date?
    public var holdCode: String?
    public var note: String?
    public var vessel: String?
    /// Исправление: id события, которое это заменяет.
    public var supersedesId: Int?

    public init(
        kind: CheckpointKind, nodeCode: String, occurredAt: Date? = nil, holdCode: String? = nil,
        note: String? = nil, vessel: String? = nil, supersedesId: Int? = nil
    ) {
        self.kind = kind
        self.nodeCode = nodeCode
        self.occurredAt = occurredAt
        self.holdCode = holdCode
        self.note = note
        self.vessel = vessel
        self.supersedesId = supersedesId
    }
}

public struct CheckpointEventRecord: Codable, Sendable, Hashable, Identifiable {
    public let id: Int
    public let kind: Coded<CheckpointKind>
    public let nodeCode: String
    public let occurredAt: Date
    public let holdCode: String?
    public let note: String?
    public let vessel: String?
    public let source: String
    public let createdBy: Int?
    public let supersedesId: Int?
    public let createdAt: Date
    /// Исправлено более поздним событием — в истории зачёркивается.
    public let superseded: Bool
}

/// Ответ на приглашение; `mail == "failed"` — приглашение создано, письмо не ушло.
public struct Invitation: Codable, Sendable, Hashable {
    public let invitationId: Int
    public let mail: String

    public var mailSent: Bool { mail == "sent" }
}

public struct OrgMember: Codable, Sendable, Hashable, Identifiable {
    public let userId: Int
    public let email: String
    public let name: String?
    public let role: Coded<AccountRole>
    public let nodeCodes: [String]

    public var id: Int { userId }
}

public struct OrgSummary: Codable, Sendable, Hashable, Identifiable {
    public let id: Int
    public let name: String
    public let kind: Coded<OrgKind>
}
