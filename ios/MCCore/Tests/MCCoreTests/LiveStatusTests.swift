import Foundation
import XCTest
@testable import MCCore

final class LiveStatusTests: XCTestCase {
    private func labels(_ lang: Lang) throws -> Labels {
        Labels(lang: lang, nodes: try Fixture.snapshot().nodes)
    }

    func test_waitingInPort() throws {
        let status = LiveStatus.make(try Fixture.shipment("MC-26-0501"), labels: try labels(.ru))
        XCTAssertEqual(status.ref, "MC-26-0501")
        XCTAssertEqual(status.leg, "Баку (Алят)")
        XCTAssertEqual(status.status, "Стоянка · +30 ч")
        XCTAssertEqual(status.phase, .stop)
        XCTAssertEqual(status.tone, .delayed)
        XCTAssertFalse(status.delivered)
    }

    func test_onFerry() throws {
        let s = try Fixture.shipment("MC-26-0501_ferry")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.ru)).leg, "Баку (Алят) → паром «Shahdag» → Актау")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.en)).leg, "Baku (Alat) → ferry “Shahdag” → Aktau")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.en)).status, "In transit · +14 h")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.ru)).phase, .sea)
    }

    func test_delivered() throws {
        var s = try Fixture.shipment("MC-26-0431")
        s.state = Coded(.delivered)
        s.progress = 1
        let status = LiveStatus.make(s, labels: try labels(.ru))
        XCTAssertTrue(status.delivered)
        XCTAssertEqual(status.progress, 1)
        XCTAssertEqual(status.phase, .done)
        XCTAssertEqual(status.leg, "Будапешт")
    }

    func test_roundTripsAsContentState() throws {
        let status = LiveStatus.make(try Fixture.shipment("MC-26-0501"), labels: try labels(.ru))
        let back = try JSONDecoder().decode(LiveStatus.self, from: JSONEncoder().encode(status))
        XCTAssertEqual(back, status)
    }
}
