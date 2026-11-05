import Foundation
import XCTest
@testable import MCCore

/// Проверка санкций: модели `/api/v1`, подписи RU/EN, группа в списке.
final class SanctionsTests: XCTestCase {
    private func labels(_ lang: Lang) throws -> Labels {
        Labels(lang: lang, nodes: try Fixture.snapshot().nodes)
    }

    private func flagged() throws -> Shipment {
        try XCTUnwrap(try Fixture.snapshot().shipments.first { $0.ref == "MC-26-0431" })
    }

    // MARK: модели

    func test_review_decodedFromFixture() throws {
        let check = try XCTUnwrap(try Fixture.shipment("MC-26-0412").sanctions)
        XCTAssertEqual(check.status.known, .review)
        XCTAssertEqual(check.lists.map(\.code), ["chpl", "eu_833_2014"])
        XCTAssertNotNil(check.checkedAt)
        let chpl = try XCTUnwrap(check.matches.first { $0.listId == "chpl" })
        XCTAssertEqual(chpl.listCode, "854231")
        XCTAssertFalse(chpl.strong)
        XCTAssertEqual(chpl.reasonCode, "code_only")
        XCTAssertTrue(check.strongMatches.isEmpty)
    }

    func test_flagged_inSnapshot() throws {
        let check = try XCTUnwrap(try flagged().sanctions)
        XCTAssertEqual(check.status.known, .flagged)
        let strong = try XCTUnwrap(check.strongMatches.first)
        XCTAssertEqual(strong.listCode, "7208")
        XCTAssertEqual(strong.lineNo, 3)
        XCTAssertEqual(strong.originCountry, "RU")
    }

    func test_absentField_isNil() throws {
        var json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: Fixture.data("shipment_MC-26-0412")) as? [String: Any])
        json["sanctions"] = nil
        let data = try JSONSerialization.data(withJSONObject: json)
        XCTAssertNil(try APIDate.makeDecoder().decode(Shipment.self, from: data).sanctions)
    }

    // MARK: подписи

    func test_statusTexts() throws {
        var check = try XCTUnwrap(try flagged().sanctions)
        XCTAssertEqual(try labels(.ru).sanctionsStatus(check), "Возможна санкционка")
        XCTAssertEqual(try labels(.en).sanctionsStatus(check), "Possible sanctioned goods")
        check.status = Coded(.missing)
        XCTAssertEqual(try labels(.ru).sanctionsStatus(check), "Нет пакинг-листа — проверить нельзя")
        check.status = Coded(.review)
        XCTAssertEqual(try labels(.en).sanctionsStatus(check), "Check manually")
        check.status = Coded(raw: "future_status")
        XCTAssertEqual(try labels(.ru).sanctionsStatus(check), "future_status")
    }

    func test_strongMatchText() throws {
        let check = try XCTUnwrap(try flagged().sanctions)
        let m = try XCTUnwrap(check.strongMatches.first)
        XCTAssertEqual(
            try labels(.ru).sanctionsMatch(m, lists: check.lists),
            "ЕС 833/2014 (прил. XVII): поз. 3, код 7208 51 100 0 — происхождение RU")
        XCTAssertEqual(
            try labels(.en).sanctionsMatch(m, lists: check.lists),
            "EU 833/2014 (Annex XVII): item 3, code 7208 51 100 0 — origin RU")
    }

    func test_weakMatchTexts() throws {
        let check = try XCTUnwrap(try Fixture.shipment("MC-26-0412").sanctions)
        XCTAssertEqual(check.matches.map(\.listId), ["chpl"])  // справочные совпадения наружу не идут
        let chpl = try XCTUnwrap(check.matches.first)
        XCTAssertEqual(
            try labels(.ru).sanctionsMatch(chpl, lists: check.lists),
            "CHPL (Tier 1): поз. 1, код 8542 31 000 1 — связи с РФ/РБ в листе нет")
    }

    func test_steelInputsText() throws {
        let check = try XCTUnwrap(try flagged().sanctions)
        var steel = try XCTUnwrap(check.strongMatches.first)
        steel.strong = false
        steel.originCountry = "CN"
        steel.reasonCode = "steel_inputs"
        XCTAssertTrue(
            try labels(.ru).sanctionsMatch(steel, lists: check.lists)
                .hasSuffix("происхождение CN — запросите происхождение стали (ст. 3g(1)(d))"))
        XCTAssertTrue(
            try labels(.en).sanctionsMatch(steel, lists: check.lists)
                .hasSuffix("origin CN — request proof of the steel inputs (Art. 3g(1)(d))"))
    }

    func test_clearFixture_hasNoMatches() throws {
        let check = try XCTUnwrap(try Fixture.shipment("MC-26-0398").sanctions)
        XCTAssertEqual(check.status.known, .clear)
        XCTAssertTrue(check.matches.isEmpty)
    }

    // MARK: набор отправленных

    func test_sentNotices_recordLoadReset() throws {
        let suite = "mc.test.sent.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let sent = SentNotices(defaults)
        XCTAssertTrue(sent.load().isEmpty)
        sent.record(["a", "b"])
        sent.record(["b", "c"])
        XCTAssertEqual(sent.load(), ["a", "b", "c"])
        sent.reset()  // сброс демо: флаг снова придёт на живом показе
        XCTAssertTrue(sent.load().isEmpty)
    }

    func test_listName_byLanguage() throws {
        let check = try XCTUnwrap(try flagged().sanctions)
        let eu = try XCTUnwrap(check.lists.first { $0.code == "eu_833_2014" })
        XCTAssertTrue(try labels(.ru).listName(eu).hasPrefix("ЕС 833/2014"))
        XCTAssertTrue(try labels(.en).listName(eu).hasPrefix("EU Regulation 833/2014"))
    }

    // MARK: группа в списке

    func test_flaggedOrMissing_isAttention() throws {
        let nodes = Dictionary(
            try Fixture.snapshot().nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        var s = try Fixture.shipment("MC-26-0412")
        XCTAssertEqual(ShipmentGroup.of(s, nodes: nodes), .active)  // review — не повод поднимать
        s.sanctions?.status = Coded(.flagged)
        XCTAssertEqual(ShipmentGroup.of(s, nodes: nodes), .attention)
        s.sanctions?.status = Coded(.missing)
        XCTAssertEqual(ShipmentGroup.of(s, nodes: nodes), .attention)
    }
}
