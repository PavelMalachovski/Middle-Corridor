import Foundation
import XCTest
@testable import MCCore

final class LabelsTests: XCTestCase {
    private func labels(_ lang: Lang) throws -> Labels {
        Labels(lang: lang, nodes: try Fixture.snapshot().nodes)
    }

    func test_eventEn_fromCodes() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(try labels(.en).event(s), "Departure: Kuryk — loaded onto ferry “Barda”")
    }

    func test_eventRu_withNoteCode_buildsFromCodes() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(try labels(.ru).event(s), "Отправление: Курык — погружен на паром «Barda»")
    }

    func test_eventRu_withoutNoteCode_usesBackendString() throws {
        var s = try Fixture.shipment("MC-26-0412")
        s.lastEventNoteCode = nil
        s.lastEvent = "Отправление: Курык"
        XCTAssertEqual(try labels(.ru).event(s), "Отправление: Курык")
    }

    func test_holdEn_weatherBan() throws {
        let s = try Fixture.shipment("MC-26-0398")
        let hold = try XCTUnwrap(try labels(.en).hold(s))
        XCTAssertTrue(hold.hasPrefix("Weather berthing ban: "), hold)
        XCTAssertFalse(hold.contains("{"), hold)
    }

    func test_unknownHoldCode_fallsBackToRussian() throws {
        var s = try Fixture.shipment("MC-26-0398")
        s.holdCode = "strike"
        s.holdReason = "Забастовка"
        XCTAssertEqual(try labels(.en).hold(s), "Забастовка")
        XCTAssertEqual(try labels(.ru).hold(s), "Забастовка")
    }

    func test_noHold_isNil() throws {
        XCTAssertNil(try labels(.en).hold(Fixture.shipment("MC-26-0412")))
    }

    func test_unknownState_showsRaw() throws {
        var s = try Fixture.shipment("MC-26-0412")
        s.state = Coded(raw: "cancelled")
        XCTAssertEqual(try labels(.en).state(s), "cancelled")
        XCTAssertEqual(s.tone, .unknown)
    }

    func test_tone() throws {
        XCTAssertEqual(try Fixture.shipment("MC-26-0398").tone, .delayed)
        XCTAssertEqual(try Fixture.shipment("MC-26-0412").tone, .inTransit)
        let delivered = try XCTUnwrap(try Fixture.snapshot().shipments.first { $0.ref == "MC-26-0322" })
        XCTAssertEqual(delivered.tone, .delivered)
    }

    func test_routeAndCargo_inEnglish() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(try labels(.en).route(s), "Xi'an → Budapest")
        XCTAssertEqual(try labels(.en).cargo(s), "2 × 40' HC, electronics")
        XCTAssertEqual(try labels(.ru).route(s), "Сиань → Будапешт")
    }

    func test_projectionIsNotFact() throws {
        var s = try Fixture.shipment("MC-26-0412")
        s.position.source = Coded(.projection)
        s.position.onVessel = nil
        s.position.confirmed = false
        let text = try labels(.en).position(s)
        XCTAssertFalse(text.confirmed)
        XCTAssertEqual(text.detail, "Schedule estimate (at sea) — no live position")
    }

    func test_aisPosition() throws {
        let text = try labels(.ru).position(Fixture.shipment("MC-26-0412"))
        XCTAssertEqual(text.title, "На пароме «Barda»")
        XCTAssertTrue(text.confirmed)
    }
}
