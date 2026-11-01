import Foundation
import XCTest
@testable import MCCore

final class LiveStatusTests: XCTestCase {
    private func labels(_ lang: Lang) throws -> Labels {
        Labels(lang: lang, nodes: try Fixture.snapshot().nodes)
    }

    func test_waitingInPort() throws {
        let status = LiveStatus.make(try Fixture.shipment("MC-26-0398"), labels: try labels(.ru))
        XCTAssertEqual(status.ref, "MC-26-0398")
        XCTAssertEqual(status.leg, "Актау")
        XCTAssertEqual(status.status, "Стоянка · +18 ч")
        XCTAssertEqual(status.phase, .stop)
        XCTAssertEqual(status.tone, .delayed)
        XCTAssertFalse(status.delivered)
    }

    func test_onFerry() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.ru)).leg, "Курык → паром «Barda» → Баку (Алят)")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.en)).leg, "Kuryk → ferry “Barda” → Baku (Alat)")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.en)).status, "In transit")
        XCTAssertEqual(LiveStatus.make(s, labels: try labels(.ru)).phase, .sea)
    }

    func test_delivered() throws {
        var s = try Fixture.shipment("MC-26-0412")
        s.state = Coded(.delivered)
        s.progress = 1
        let status = LiveStatus.make(s, labels: try labels(.ru))
        XCTAssertTrue(status.delivered)
        XCTAssertEqual(status.progress, 1)
        XCTAssertEqual(status.phase, .done)
        XCTAssertEqual(status.leg, "Будапешт")
    }

    func test_roundTripsAsContentState() throws {
        let status = LiveStatus.make(try Fixture.shipment("MC-26-0398"), labels: try labels(.ru))
        let back = try JSONDecoder().decode(LiveStatus.self, from: JSONEncoder().encode(status))
        XCTAssertEqual(back, status)
    }
}
