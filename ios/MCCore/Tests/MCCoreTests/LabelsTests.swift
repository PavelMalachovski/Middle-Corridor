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

    private func queue(p50: Double, p90: Double) -> QueueForecast {
        QueueForecast(
            portCode: "AKTAU", position: 4, perDay: 8, weatherHours: 0, p50Hours: p50, p90Hours: p90,
            basisCode: "ferry_wait")
    }

    func test_queueLabels_days() throws {
        let q = queue(p50: 60, p90: 120)
        XCTAssertEqual(try labels(.ru).queue(q).main, "2–3 дня")
        XCTAssertEqual(try labels(.ru).queue(q).worst, "до 5 дней")
        XCTAssertEqual(try labels(.en).queue(q).main, "2–3 days")
        XCTAssertEqual(try labels(.en).queue(q).worst, "up to 5 days")
    }

    func test_queueLabels_hours() throws {
        let q = queue(p50: 12, p90: 24)
        XCTAssertEqual(try labels(.ru).queue(q).main, "≈ 12 ч")
        XCTAssertEqual(try labels(.ru).queue(q).worst, "до 1 дня")
        XCTAssertEqual(try labels(.en).queue(q).main, "≈ 12 h")
        XCTAssertEqual(try labels(.en).queue(q).worst, "up to 1 day")
    }

    func test_queueLabels_exactDays_andPlurals() throws {
        XCTAssertEqual(try labels(.ru).queue(queue(p50: 48, p90: 100)).main, "2 дня")
        XCTAssertEqual(try labels(.ru).queue(queue(p50: 100, p90: 130)).main, "4–5 дней")
        XCTAssertEqual(try labels(.ru).queue(queue(p50: 20, p90: 20)).worst, "до 20 ч")
        XCTAssertEqual(try labels(.ru).queue(queue(p50: 24, p90: 48)).main, "1 день")
        XCTAssertEqual(try labels(.en).queue(queue(p50: 24, p90: 48)).main, "1 day")
    }
}
