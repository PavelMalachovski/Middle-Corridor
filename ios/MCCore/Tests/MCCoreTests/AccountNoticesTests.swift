import Foundation
import XCTest

@testable import MCCore

/// Уведомления по грузам аккаунта: штормы по узлам «было → стало», push глушит только «событие»;
/// нажатие на уведомление — куда вести.
final class AccountNoticesTests: XCTestCase {
    private var nodes: [NodeStatus] = []
    private var mine: [MyShipment] = []

    override func setUpWithError() throws {
        nodes = try Fixture.snapshot().nodes
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: "my_shipments", withExtension: "json", subdirectory: "Fixtures/account"))
        mine = try APIDate.makeDecoder().decode([MyShipment].self, from: Data(contentsOf: url))
    }

    private func level(_ code: String, _ level: AlertLevel?) -> [NodeStatus] {
        nodes.map { node in
            var copy = node
            if node.code == code { copy.alertLevel = level.map { Coded($0) } }
            return copy
        }
    }

    /// Тот же груз с другим последним событием (новость для «события»).
    private func withNewEvent(_ m: MyShipment) throws -> MyShipment {
        let json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: APIDate.makeEncoder().encode(m)) as? [String: Any])
        var dict = json
        var s = try XCTUnwrap(dict["shipment"] as? [String: Any])
        s["last_event_kind"] = "departed"
        s["last_event"] = "Отправление: Актау"
        s["last_event_at"] = "2027-03-09T10:00:00Z"
        dict["shipment"] = s
        return try APIDate.makeDecoder().decode(MyShipment.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func diff(
        old: [MyShipment], new: [MyShipment], oldNodes: [NodeStatus], newNodes: [NodeStatus], push: Bool = false
    ) -> [AppNotice] {
        NotificationRules.accountDiff(
            old: old, new: new, oldNodes: oldNodes, newNodes: newNodes, settings: .all,
            labels: Labels(lang: .ru, nodes: newNodes), pushRegistered: push)
    }

    func test_stormEscalationAtAccountShipmentNode_notifies() {
        let notices = diff(
            old: mine, new: mine, oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        XCTAssertEqual(notices.map(\.kind), [.storm])
        XCTAssertEqual(notices.first?.ref, "MC-27-0001")
    }

    func test_sameNodes_noStorm() {
        let critical = level("AKTAU", .critical)
        XCTAssertTrue(diff(old: mine, new: mine, oldNodes: critical, newNodes: critical).isEmpty)
    }

    func test_pushRegistered_silencesEventButNotStorm() throws {
        let moved = [try withNewEvent(mine[0])]
        let local = diff(old: mine, new: moved, oldNodes: nodes, newNodes: nodes)
        XCTAssertEqual(local.map(\.kind), [.event])
        XCTAssertTrue(diff(old: mine, new: moved, oldNodes: nodes, newNodes: nodes, push: true).isEmpty)
        let storm = diff(
            old: mine, new: moved, oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical), push: true)
        XCTAssertEqual(storm.map(\.kind), [.storm])
    }

    func test_firstLoad_isSilent() {
        XCTAssertTrue(
            diff(old: [], new: mine, oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical)).isEmpty)
    }

    // MARK: - Нажатие на уведомление

    func test_target_knownAccountRef_opensAccountCard() {
        XCTAssertEqual(
            AccountRows.notificationTarget("MC-27-0001", in: mine, signedIn: true, refreshed: false),
            .account(AccountRows.key(mine[0])))
    }

    /// Список аккаунта непустой, но устарел: нового груза в нём нет — сначала обновить, а не в демо-номера.
    func test_target_unknownRef_staleList_refreshesFirst() {
        XCTAssertEqual(AccountRows.notificationTarget("MC-27-0099", in: mine, signedIn: true, refreshed: false), .refresh)
        XCTAssertEqual(AccountRows.notificationTarget("MC-27-0099", in: [], signedIn: true, refreshed: false), .refresh)
        XCTAssertEqual(
            AccountRows.notificationTarget("MC-27-0099", in: mine, signedIn: true, refreshed: true), .tracked("MC-27-0099"))
    }

    func test_target_signedOut_tracked() {
        XCTAssertEqual(
            AccountRows.notificationTarget("MC-27-0001", in: mine, signedIn: false, refreshed: false),
            .tracked("MC-27-0001"))
    }
}
