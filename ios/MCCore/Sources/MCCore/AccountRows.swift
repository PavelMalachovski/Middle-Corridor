import Foundation

/// Строки грузов аккаунта в «Моих грузах». Ключ строки и навигации — `acct:<org>:<номер>`:
/// номер груза аккаунта может совпасть с отслеживаемым демо-номером, и по одному номеру
/// пользователь увидел бы демо вместо своего груза.
public enum AccountRows {
    static let prefix = "acct:"

    public static func key(orgId: Int, ref: String) -> String { "\(prefix)\(orgId):\(ref)" }

    public static func key(_ shipment: MyShipment) -> String {
        key(orgId: shipment.orgId, ref: shipment.shipment.ref)
    }

    /// Ключ груза аккаунта → компания и номер; обычный номер — nil.
    public static func parse(_ key: String) -> (orgId: Int, ref: String)? {
        guard key.hasPrefix(prefix) else { return nil }
        let rest = key.dropFirst(prefix.count)
        guard let colon = rest.firstIndex(of: ":"), let orgId = Int(rest[..<colon]) else { return nil }
        let ref = String(rest[rest.index(after: colon)...])
        return ref.isEmpty ? nil : (orgId, ref)
    }

    /// Сначала отслеживаемые номера, затем грузы аккаунта — каждый своей строкой.
    public static func merge(local: [TrackedRow], account: [MyShipment]) -> [TrackedRow] {
        local + account.map { TrackedRow(ref: $0.shipment.ref, shipment: $0.shipment, id: key($0)) }
    }

    public static func find(_ key: String, in shipments: [MyShipment]) -> MyShipment? {
        guard let parsed = parse(key) else { return nil }
        return shipments.first { $0.orgId == parsed.orgId && $0.shipment.ref == parsed.ref }
    }

    /// Куда ведёт нажатие на уведомление (локальное или push `{"ref": …}`).
    public enum NotificationTarget: Equatable, Sendable {
        /// Карточка груза аккаунта (ключ `acct:`).
        case account(String)
        /// Номера нет в списке аккаунта — список мог устареть (новый или открытый клиенту груз):
        /// обновить и спросить снова с `refreshed: true`.
        case refresh
        /// Отслеживаемый номер (демо).
        case tracked(String)
    }

    public static func notificationTarget(
        _ ref: String, in shipments: [MyShipment], signedIn: Bool, refreshed: Bool
    ) -> NotificationTarget {
        guard signedIn else { return .tracked(ref) }
        if let mine = shipments.first(where: { $0.shipment.ref == ref }) { return .account(key(mine)) }
        return refreshed ? .tracked(ref) : .refresh
    }
}
