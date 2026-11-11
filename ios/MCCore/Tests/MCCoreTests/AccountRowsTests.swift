import Foundation
import XCTest

@testable import MCCore

final class AccountRowsTests: XCTestCase {
    private func accountShipments() throws -> [MyShipment] {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: "my_shipments", withExtension: "json", subdirectory: "Fixtures/account"))
        return try APIDate.makeDecoder().decode([MyShipment].self, from: Data(contentsOf: url))
    }

    func test_key_roundTrip() {
        let key = AccountRows.key(orgId: 7, ref: "MC-27-0001")
        XCTAssertEqual(key, "acct:7:MC-27-0001")
        let parsed = AccountRows.parse(key)
        XCTAssertEqual(parsed?.orgId, 7)
        XCTAssertEqual(parsed?.ref, "MC-27-0001")
        XCTAssertNil(AccountRows.parse("MC-27-0001"))
        XCTAssertNil(AccountRows.parse("acct:x:MC-27-0001"))
    }

    /// Номер груза аккаунта совпал с отслеживаемым демо-номером: строк две, id разные,
    /// у аккаунтной — ключ `acct:`, номер — тот же.
    func test_merge_sameRefAsLocal_keepsBothRows() throws {
        let mine = try accountShipments()
        let ref = try XCTUnwrap(mine.first?.shipment.ref)
        let local = [TrackedRow(ref: ref, shipment: try Fixture.shipment("MC-26-0431"))]
        let rows = AccountRows.merge(local: local, account: mine)
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(Set(rows.map(\.id)).count, 2)
        XCTAssertEqual(rows.map(\.ref), [ref, ref])
        XCTAssertEqual(rows[0].id, ref)
        XCTAssertEqual(rows[1].id, AccountRows.key(orgId: mine[0].orgId, ref: ref))
        XCTAssertEqual(rows[1].shipment, mine[0].shipment)

        let sections = ShipmentGroup.group(rows, nodes: [])
        XCTAssertEqual(sections.flatMap(\.rows).count, 2)
    }

    func test_find_byKey() throws {
        let mine = try accountShipments()
        let first = try XCTUnwrap(mine.first)
        XCTAssertEqual(AccountRows.find(AccountRows.key(orgId: first.orgId, ref: first.shipment.ref), in: mine), first)
        XCTAssertNil(AccountRows.find(AccountRows.key(orgId: first.orgId + 1, ref: first.shipment.ref), in: mine))
        XCTAssertNil(AccountRows.find(first.shipment.ref, in: mine))
    }
}
