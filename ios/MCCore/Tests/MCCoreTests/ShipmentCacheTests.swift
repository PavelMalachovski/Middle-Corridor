import Foundation
import XCTest
@testable import MCCore

final class ShipmentCacheTests: XCTestCase {
    private var dir: URL!

    override func setUpWithError() throws {
        dir = FileManager.default.temporaryDirectory.appending(path: "mc-cache-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    func test_fileCache_roundTrip() throws {
        let s = try Fixture.shipment("MC-26-0412")
        let state = CachedState(
            shipments: [s.ref: s], snapshot: try Fixture.snapshot(), updatedAt: Date(timeIntervalSince1970: 5000))
        FileShipmentCache(directory: dir).save(state)

        let loaded = try XCTUnwrap(FileShipmentCache(directory: dir).load())
        XCTAssertEqual(Set(loaded.shipments.keys), ["MC-26-0412"])
        XCTAssertEqual(loaded.updatedAt, Date(timeIntervalSince1970: 5000))
        XCTAssertEqual(loaded.snapshot?.nodes.count, state.snapshot?.nodes.count)
    }

    func test_fileCache_empty_returnsNil() {
        XCTAssertNil(FileShipmentCache(directory: dir).load())
    }

    func test_fileCache_corrupt_returnsNil() throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Data("{not json".utf8).write(to: dir.appending(path: FileShipmentCache.fileName))
        XCTAssertNil(FileShipmentCache(directory: dir).load())
    }

    func test_fileCache_missingNewField_decodes() throws {
        // кэш, записанный до появления queue/forecast/thresholds
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let shipment = try XCTUnwrap(String(data: Fixture.data("shipment_MC-26-0412"), encoding: .utf8))
        let old = #"{"shipments":{"MC-26-0412":\#(shipment)},"updated_at":"2026-10-31T11:00:00Z"}"#
        try Data(old.utf8).write(to: dir.appending(path: FileShipmentCache.fileName))
        let loaded = try XCTUnwrap(FileShipmentCache(directory: dir).load())
        XCTAssertNil(loaded.shipments["MC-26-0412"]?.queue)
        XCTAssertNil(loaded.snapshot)
    }
}
