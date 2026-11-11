import Foundation
import XCTest
@testable import MCCore

final class ShipmentRefTests: XCTestCase {
    func test_parse_normalizesInput() {
        XCTAssertEqual(ShipmentRef.parse(" mc-26-0501\n"), "MC-26-0501")
        XCTAssertEqual(ShipmentRef.parse("MC-26-0501"), "MC-26-0501")
    }

    func test_parse_findsRefInsideText() {
        XCTAssertEqual(ShipmentRef.parse("ваш груз MC-26-0501 отправлен"), "MC-26-0501")
        XCTAssertEqual(ShipmentRef.parse("https://x.app/?s=MC-26-0501&view=map"), "MC-26-0501")
    }

    func test_parse_rejectsGarbage() {
        XCTAssertNil(ShipmentRef.parse("hello"))
        XCTAssertNil(ShipmentRef.parse(""))
        XCTAssertNil(ShipmentRef.parse("MC-26"))
    }

    func test_fromURL_customScheme() throws {
        XCTAssertEqual(ShipmentRef.from(url: try XCTUnwrap(URL(string: "mcstatus://s/mc-26-0501"))), "MC-26-0501")
        XCTAssertNil(ShipmentRef.from(url: try XCTUnwrap(URL(string: "mcstatus://other/MC-26-0501"))))
    }

    func test_fromURL_webLink() throws {
        XCTAssertEqual(
            ShipmentRef.from(url: try XCTUnwrap(URL(string: "https://x.app/?s=MC-26-0501&view=map"))),
            "MC-26-0501"
        )
        XCTAssertNil(ShipmentRef.from(url: try XCTUnwrap(URL(string: "https://x.app/?view=map"))))
    }

    func test_shareURL() throws {
        let base = try XCTUnwrap(URL(string: "https://x.app"))
        XCTAssertEqual(ShipmentRef.shareURL(ref: "MC-26-0501", base: base).absoluteString, "https://x.app/?s=MC-26-0501")
    }
}
