import Foundation
import XCTest
@testable import MCCore

final class ModelsTests: XCTestCase {
    func test_decodesShipmentFixture() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(s.ref, "MC-26-0412")
        XCTAssertEqual(s.id, "MC-26-0412")
        XCTAssertEqual(s.state.known, .inTransit)
        XCTAssertEqual(s.position.source.known, .ais)
        XCTAssertTrue(s.position.confirmed)
        XCTAssertEqual(s.position.onVessel, "Barda")
        XCTAssertEqual(s.position.mode?.known, .sea)
        XCTAssertEqual(s.checkpoints.first?.code, "XIAN")
        XCTAssertEqual(s.checkpoints.first?.state.known, .done)
        XCTAssertEqual(s.lastEventKind?.known, .departed)
        XCTAssertEqual(s.lastEventNoteCode, "loaded_on_ferry")
        XCTAssertNotNil(s.eta)
        XCTAssertGreaterThan(s.track.count, 10)
        XCTAssertEqual(s.cargoEn, "2 × 40' HC, electronics")
    }

    func test_decodesSnapshotFixture() throws {
        let snap = try Fixture.snapshot()
        XCTAssertEqual(snap.nodes.count, 18)
        XCTAssertEqual(snap.shipments.count, 3)
        XCTAssertEqual(snap.summary?.caspianCrossings, 3)
        XCTAssertEqual(snap.nodes.first?.nameEn, "Xi'an")
        XCTAssertTrue(snap.mock)
        XCTAssertEqual(snap.news.count, 3)
    }

    func test_parsesMicrosecondsAndPlainDates() throws {
        let micro = try XCTUnwrap(APIDate.parse("2026-10-31T11:08:54.312620Z"))
        XCTAssertEqual(micro.timeIntervalSince1970, 1_793_444_934.31262, accuracy: 0.001)
        XCTAssertEqual(APIDate.parse("2026-10-31T11:00:00Z")?.timeIntervalSince1970, 1_793_444_400)
        XCTAssertEqual(
            APIDate.parse("2026-10-31T11:00:00+04:00")?.timeIntervalSince1970,
            1_793_444_400 - 4 * 3600
        )
        XCTAssertEqual(APIDate.parse("1970-01-01T00:00:00Z")?.timeIntervalSince1970, 0)
        XCTAssertNil(APIDate.parse("bad"))
        XCTAssertNil(APIDate.parse("2026-13-01T00:00:00Z"))
        XCTAssertNil(APIDate.parse("2026-10-31T11:00:00Zjunk"))
    }

    func test_unknownStateDoesNotFail() throws {
        var json = try XCTUnwrap(String(data: Fixture.data("shipment_MC-26-0412"), encoding: .utf8))
        let range = try XCTUnwrap(json.range(of: "\"state\": \"in_transit\""))
        json.replaceSubrange(range, with: "\"state\": \"cancelled\"")
        let s = try APIDate.makeDecoder().decode(Shipment.self, from: Data(json.utf8))
        XCTAssertEqual(s.state.raw, "cancelled")
        XCTAssertNil(s.state.known)
    }

    func test_shipmentRoundTripsThroughEncoder() throws {
        let s = try Fixture.shipment("MC-26-0398")
        let data = try APIDate.makeEncoder().encode(s)
        let back = try APIDate.makeDecoder().decode(Shipment.self, from: data)
        XCTAssertEqual(back, s)
    }
}
