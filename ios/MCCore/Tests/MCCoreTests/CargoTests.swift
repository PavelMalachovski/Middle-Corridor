import Foundation
import XCTest
@testable import MCCore

/// Блок «Груз»: контейнер, места, вес, опасный груз, главные позиции.
final class CargoTests: XCTestCase {
    func test_eastbound_cargoDecoded() throws {
        let s = try XCTUnwrap(try Fixture.snapshot().shipments.first { $0.ref == "MC-26-0501" })
        let c = try XCTUnwrap(s.cargoDetails)
        XCTAssertEqual(c.containerType, "40' HC")
        XCTAssertEqual(c.packages, 14)
        XCTAssertEqual(c.packageKind, "поддоны")
        XCTAssertEqual(c.dangerous.map(\.unNumber), ["2800"])
        XCTAssertEqual(c.dangerous.first?.hazardClass, "8")
        XCTAssertEqual(c.topItems.count, 5)
        XCTAssertEqual(c.moreItems, 4)
        XCTAssertEqual(c.topItems.first?.netKg, 5481)
    }

    func test_absentField_isNil() throws {
        var json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: Fixture.data("shipment_MC-26-0412")) as? [String: Any])
        json["cargo_details"] = nil
        let data = try JSONSerialization.data(withJSONObject: json)
        XCTAssertNil(try APIDate.makeDecoder().decode(Shipment.self, from: data).cargoDetails)
    }
}
