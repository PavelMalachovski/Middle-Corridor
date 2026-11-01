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

    func test_decodesQueue() throws {
        let queue = try XCTUnwrap(Fixture.shipment("MC-26-0398").queue)
        XCTAssertEqual(queue.p50Hours, 60)
        XCTAssertEqual(queue.p90Hours, 120)
        XCTAssertEqual(queue.basisCode, "weather_ban")
        XCTAssertEqual(queue.portCode, "AKTAU")
        let inSnapshot = try Fixture.snapshot().shipments.first { $0.ref == "MC-26-0398" }
        XCTAssertEqual(inSnapshot?.queue, queue)
    }

    func test_decodesForecastAndThresholds() throws {
        let snapshot = try Fixture.snapshot()
        let aktau = try XCTUnwrap(snapshot.nodes.first { $0.code == "AKTAU" })
        XCTAssertEqual(aktau.forecast?.count, 55)
        XCTAssertEqual(aktau.forecast?.first?.level?.known, .critical)
        XCTAssertNotNil(aktau.alertMessage)
        XCTAssertEqual(snapshot.thresholds?.criticalWind, 17)
        XCTAssertEqual(snapshot.thresholds?.warningWind, 13.8)
    }

    func test_oldPayloadWithoutNewFields() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertNil(s.queue)
        let bare = #"{"generated_at":"2026-10-31T11:00:00Z","server_time":"2026-10-31T11:00:00Z","replay":false,"mock":true,"nodes":[],"shipments":[],"news":[]}"#
        let snapshot = try APIDate.makeDecoder().decode(MapSnapshot.self, from: Data(bare.utf8))
        XCTAssertNil(snapshot.thresholds)
    }

    func test_decodesDemoClock() throws {
        let json = #"{"now":"2026-11-01T10:00:00Z","offset_hours":6,"story_start":"2026-11-01T04:00:00.123456Z","story_ref":"MC-26-0398"}"#
        let state = try APIDate.makeDecoder().decode(DemoClockState.self, from: Data(json.utf8))
        XCTAssertEqual(state.offsetHours, 6)
        XCTAssertEqual(state.storyRef, "MC-26-0398")
    }
}
