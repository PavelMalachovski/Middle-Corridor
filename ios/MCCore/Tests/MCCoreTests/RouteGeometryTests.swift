import Foundation
import XCTest
@testable import MCCore

final class RouteGeometryTests: XCTestCase {
    // трек вдоль экватора: (lon 0…3, lat 0) — порядок [lon, lat]
    private let track: [[Double]] = [[0, 0], [1, 0], [2, 0], [3, 0]]

    private func position(lat: Double, lon: Double, progress: Double = 0.5) -> ShipmentPosition {
        ShipmentPosition(
            lat: lat, lon: lon, heading: nil, confirmed: false, source: Coded(.projection),
            onVessel: nil, mode: Coded(.rail), fromCode: "A", toCode: "B", legProgress: progress)
    }

    func test_split_midLeg() {
        let p = position(lat: 0, lon: 1.5)
        let (done, rest) = RouteGeometry.split(track: track, at: p, state: .inTransit)
        XCTAssertEqual(done, [GeoPoint(lat: 0, lon: 0), GeoPoint(lat: 0, lon: 1), GeoPoint(lat: 0, lon: 1.5)])
        XCTAssertEqual(rest, [GeoPoint(lat: 0, lon: 1.5), GeoPoint(lat: 0, lon: 2), GeoPoint(lat: 0, lon: 3)])
        XCTAssertEqual(done.last, rest.first)
    }

    func test_split_atStart() {
        let p = position(lat: 0, lon: 0, progress: 0)
        let (done, rest) = RouteGeometry.split(track: track, at: p, state: .planned)
        XCTAssertEqual(done, [GeoPoint(lat: 0, lon: 0)])
        XCTAssertEqual(rest.count, 4)
    }

    func test_split_atVertex_notDuplicated() {
        let p = position(lat: 0, lon: 2)
        let (done, rest) = RouteGeometry.split(track: track, at: p, state: .waiting)
        XCTAssertEqual(done.count, 3)
        XCTAssertEqual(rest.count, 2)
        XCTAssertEqual(done.last, GeoPoint(lat: 0, lon: 2))
        XCTAssertEqual(rest.first, GeoPoint(lat: 0, lon: 2))
    }

    func test_split_delivered() {
        let p = position(lat: 0, lon: 3, progress: 1)
        let (done, rest) = RouteGeometry.split(track: track, at: p, state: .delivered)
        XCTAssertEqual(done.count, 4)
        XCTAssertTrue(rest.isEmpty)
    }

    func test_split_emptyTrack() {
        let (done, rest) = RouteGeometry.split(track: [], at: position(lat: 0, lon: 0), state: .inTransit)
        XCTAssertTrue(done.isEmpty && rest.isEmpty)
    }

    func test_split_fixture0501OnFerry() throws {
        let s = try Fixture.shipment("MC-26-0501_ferry")
        let (done, rest) = RouteGeometry.split(track: s.track, at: s.position, state: s.state.known)
        XCTAssertEqual(done.count + rest.count, s.track.count + 2)
        XCTAssertEqual(done.last, GeoPoint(lat: s.position.lat, lon: s.position.lon))
    }

    /// Такт «шторм»: груз ждёт в Аляте, а погодный запрет — в Актау: показываем погоду Актау.
    func test_weatherPort_weatherBan_isBanPort() throws {
        let s = try Fixture.shipment("MC-26-0501")
        XCTAssertEqual(s.holdCode, "weather_ban")
        let port = RouteGeometry.weatherPort(for: s, nodes: try Fixture.snapshot().nodes)
        XCTAssertEqual(port?.code, "AKTAU")
    }

    func test_weatherPort_waitingWithoutBan_isCurrentPort() throws {
        var s = try Fixture.shipment("MC-26-0501")
        s.holdCode = "ferry_loading_wait"
        s.holdNode = "BAKU_ALAT"
        XCTAssertEqual(RouteGeometry.weatherPort(for: s, nodes: try Fixture.snapshot().nodes)?.code, "BAKU_ALAT")
        s.holdCode = "weather_ban"
        s.holdNode = "BEINEU"  // не порт — правило запрета не действует
        XCTAssertEqual(RouteGeometry.weatherPort(for: s, nodes: try Fixture.snapshot().nodes)?.code, "BAKU_ALAT")
    }

    func test_weatherPort_atSea_isNextPort() throws {
        let s = try Fixture.shipment("MC-26-0501_ferry")
        let port = RouteGeometry.weatherPort(for: s, nodes: try Fixture.snapshot().nodes)
        XCTAssertEqual(port?.code, "AKTAU")
    }

    func test_weatherPort_noTrackedPorts_isNil() throws {
        let s = try Fixture.shipment("MC-26-0501_ferry")
        XCTAssertNil(RouteGeometry.weatherPort(for: s, nodes: []))
    }
}
