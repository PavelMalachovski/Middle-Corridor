import Foundation
import XCTest
@testable import MCCore

/// Неделя 5: вилка ETA, разбор задержки, точность, паромы и сегменты для карты.
final class Week5Tests: XCTestCase {
    private func labels(_ lang: Lang) throws -> Labels { Labels(lang: lang, nodes: try Fixture.snapshot().nodes) }

    func test_decodesEtaRangeAndBreakdown() throws {
        let s = try Fixture.shipment("MC-26-0398")
        let eta = try XCTUnwrap(s.eta), latest = try XCTUnwrap(s.etaLatest)
        XCTAssertEqual(latest.timeIntervalSince(eta), 60 * 3600, accuracy: 1)
        XCTAssertEqual(s.delayBreakdown?.first?.code, "weather_ban")
        XCTAssertEqual(s.delayBreakdown?.first?.hours, 18)
    }

    func test_decodesVesselsAndSegments() throws {
        let snap = try Fixture.snapshot()
        XCTAssertGreaterThan(snap.vessels?.count ?? 0, 0)
        XCTAssertGreaterThan(snap.segments?.first?.coordinates.count ?? 0, 1)
    }

    func test_decodesAccuracy() throws {
        let report = try APIDate.makeDecoder().decode(AccuracyReport.self, from: Fixture.data("accuracy"))
        XCTAssertEqual(report.demo, true)
        XCTAssertEqual(report.days, 90)
        XCTAssertTrue(report.ports.contains { $0.code == "AKTAU" })
    }

    func test_oldShipmentWithoutNewFields() throws {
        let s = try Fixture.shipment("MC-26-0412")
        XCTAssertNil(s.etaLatest)
        XCTAssertNil(s.delayBreakdown)
    }

    func test_delayPart_labels() throws {
        let ru = try labels(.ru), en = try labels(.en)
        XCTAssertEqual(ru.delayPart(DelayPart(code: "weather_ban", nodeCode: "AKTAU", hours: 18)), "Погодный запрет: Актау")
        XCTAssertEqual(ru.delayPart(DelayPart(code: "ferry_wait", nodeCode: "AKTAU", hours: 6)), "Ожидание парома: Актау")
        XCTAssertEqual(ru.delayPart(DelayPart(code: "schedule", nodeCode: nil, hours: 2)), "Отставание от графика")
        XCTAssertEqual(en.delayPart(DelayPart(code: "weather_ban", nodeCode: "AKTAU", hours: 18)), "Weather ban: Aktau")
        XCTAssertEqual(ru.delayPart(DelayPart(code: "mystery", nodeCode: nil, hours: 1)), "mystery")
    }

    func test_etaRange() throws {
        let ru = try labels(.ru)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        func d(_ month: Int, _ day: Int, _ hour: Int = 12) -> Date {
            utc.date(from: DateComponents(year: 2026, month: month, day: day, hour: hour))!
        }
        XCTAssertEqual(ru.etaRange(d(11, 7), d(11, 7, 20), timeZone: utc.timeZone), "7 нояб.")
        XCTAssertEqual(ru.etaRange(d(11, 7), d(11, 9), timeZone: utc.timeZone), "7–9 нояб.")
        XCTAssertEqual(ru.etaRange(d(11, 30), d(12, 2), timeZone: utc.timeZone), "30 нояб. – 2 дек.")
        XCTAssertEqual(ru.etaRange(d(11, 7), nil, timeZone: utc.timeZone), "7 нояб.")
    }

    func test_accuracySummary() throws {
        let report = try APIDate.makeDecoder().decode(AccuracyReport.self, from: Fixture.data("accuracy"))
        let summary = AccuracySummary.make(report)
        XCTAssertEqual(summary.closures, report.ports.map(\.closures).reduce(0, +))
        XCTAssertEqual(summary.hits, report.ports.map(\.hits).reduce(0, +))
        XCTAssertNotNil(summary.medianLeadH)
        let text = try labels(.ru).accuracy(summary)
        XCTAssertTrue(text.main.hasPrefix("Предупредили о \(summary.hits) из \(summary.closures)"), text.main)
        XCTAssertTrue(text.detail.contains("ложных тревог"), text.detail)
    }

    func test_accuracySummary_noData() {
        let empty = AccuracyReport(since: Date(), until: Date(), days: 90, ports: [], demo: true)
        let summary = AccuracySummary.make(empty)
        XCTAssertEqual(summary.closures, 0)
        XCTAssertNil(summary.medianLeadH)
    }

    func test_liveVessels_filtersNoPosition() {
        let v = [
            VesselStatus(name: "A", lat: 41, lon: 50, cog: 270, sog: 10, hasRecentData: true, route: nil, phaseCode: nil),
            VesselStatus(name: "B", lat: nil, lon: nil, cog: nil, sog: nil, hasRecentData: false, route: nil, phaseCode: nil),
            VesselStatus(name: "C", lat: 41, lon: 50, cog: nil, sog: nil, hasRecentData: false, route: nil, phaseCode: nil),
        ]
        XCTAssertEqual(CorridorMap.liveVessels(v).map(\.name), ["A"])
    }
}
