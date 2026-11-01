import Foundation
import XCTest
@testable import MCCore

final class ShipmentGroupsTests: XCTestCase {
    private func nodes() throws -> [String: NodeStatus] {
        Dictionary(try Fixture.snapshot().nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
    }

    func test_delayedWithHold_isAttention() throws {
        XCTAssertEqual(ShipmentGroup.of(try Fixture.shipment("MC-26-0398"), nodes: try nodes()), .attention)
    }

    func test_inTransitWithoutStormAhead_isActive() throws {
        XCTAssertEqual(ShipmentGroup.of(try Fixture.shipment("MC-26-0412"), nodes: try nodes()), .active)
    }

    func test_delivered_isDelivered() throws {
        let delivered = try XCTUnwrap(try Fixture.snapshot().shipments.first { $0.state.known == .delivered })
        XCTAssertEqual(ShipmentGroup.of(delivered, nodes: try nodes()), .delivered)
    }

    func test_stormAtPortAhead_raisesToAttention() throws {
        var s = try Fixture.shipment("MC-26-0412")
        var all = try nodes()
        all["POTI"]?.alertLevel = Coded(.warning)
        XCTAssertEqual(ShipmentGroup.of(s, nodes: all), .attention)
        all["POTI"]?.alertLevel = Coded(.watch)  // «усиление ветра» — ещё не повод
        XCTAssertEqual(ShipmentGroup.of(s, nodes: all), .active)
        s.state = Coded(.delivered)
        all["POTI"]?.alertLevel = Coded(.critical)
        XCTAssertEqual(ShipmentGroup.of(s, nodes: all), .delivered)
    }

    func test_plannedWithoutProblems_isPlanned() throws {
        var s = try Fixture.shipment("MC-26-0412")
        s.state = Coded(.planned)
        XCTAssertEqual(ShipmentGroup.of(s, nodes: [:]), .planned)
        s.delayHours = 5
        XCTAssertEqual(ShipmentGroup.of(s, nodes: [:]), .attention)
    }

    func test_group_ordersSectionsAndKeepsListOrder() throws {
        let snapshot = try Fixture.snapshot()
        let delivered = try XCTUnwrap(snapshot.shipments.first { $0.state.known == .delivered })
        let rows = [
            TrackedRow(ref: "MC-26-0412", shipment: try Fixture.shipment("MC-26-0412")),
            TrackedRow(ref: delivered.ref, shipment: delivered),
            TrackedRow(ref: "MC-26-0398", shipment: try Fixture.shipment("MC-26-0398")),
            TrackedRow(ref: "MC-26-9999", shipment: nil),
            TrackedRow(ref: "MC-26-0001", shipment: nil),
        ]
        let groups = ShipmentGroup.group(rows, nodes: snapshot.nodes, missing: ["MC-26-9999"])
        XCTAssertEqual(groups.map(\.group), [.attention, .active, .delivered])
        XCTAssertEqual(groups[0].rows.map(\.ref), ["MC-26-0398", "MC-26-9999"])
        XCTAssertEqual(groups[1].rows.map(\.ref), ["MC-26-0412", "MC-26-0001"])
        XCTAssertEqual(groups[2].rows.map(\.ref), [delivered.ref])
    }
}

final class CheckpointWindowTests: XCTestCase {
    func test_fixture0398_showsPreviousCurrentAndThreeAhead() throws {
        let window = CheckpointWindow(try Fixture.shipment("MC-26-0398").checkpoints)
        XCTAssertEqual(window.visible, 6...10)  // Бейнеу, Актау, Баку, Гянджа, Бёюк-Кясик
        XCTAssertEqual(window.hiddenBefore, 6)
        XCTAssertEqual(window.hiddenAfter, 3)
    }

    func test_singleHiddenPoint_isShownInstead() {
        let states: [CheckpointState?] = [.done, .done, .current, .planned, .planned, .planned, .planned]
        let window = CheckpointWindow(states: states)
        XCTAssertEqual(window.visible, 0...6)
        XCTAssertEqual(window.hiddenBefore, 0)
        XCTAssertEqual(window.hiddenAfter, 0)
    }

    func test_delivered_collapsesAllButLast() {
        let window = CheckpointWindow(states: Array(repeating: .done, count: 10))
        XCTAssertEqual(window.visible, 8...9)
        XCTAssertEqual(window.hiddenBefore, 8)
        XCTAssertEqual(window.hiddenAfter, 0)
    }

    func test_notStarted_showsFirstPoints() {
        let window = CheckpointWindow(states: Array(repeating: .planned, count: 10))
        XCTAssertEqual(window.visible, 0...3)
        XCTAssertEqual(window.hiddenAfter, 6)
    }

    func test_empty() {
        let window = CheckpointWindow(states: [])
        XCTAssertEqual(window.hiddenBefore, 0)
        XCTAssertEqual(window.hiddenAfter, 0)
    }
}

final class WindOutlookTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 1_800_000_000)

    private func hour(_ h: Int, _ speed: Double, _ level: AlertLevel?) -> WindHour {
        WindHour(ts: t0.addingTimeInterval(Double(h) * 3600), speed: speed, gust: speed * 1.4, level: level.map { Coded($0) })
    }

    func test_worstLevelAhead_untilLastHourAtThatLevel() {
        let hours = [hour(-2, 25, .critical), hour(0, 15, .warning), hour(1, 18, .critical), hour(2, 12, .watch)]
        let outlook = WindOutlook(hours: hours, now: t0)
        XCTAssertEqual(outlook.level, .critical)
        XCTAssertEqual(outlook.peak, 18)  // прошлое не считается
        XCTAssertEqual(outlook.until, t0.addingTimeInterval(3600))
    }

    func test_levelHoldsToTheEnd_untilIsNil() {
        let outlook = WindOutlook(hours: [hour(0, 18, .critical), hour(1, 19, .critical)], now: t0)
        XCTAssertEqual(outlook.level, .critical)
        XCTAssertNil(outlook.until)
    }

    func test_calm() {
        let outlook = WindOutlook(hours: [hour(0, 5, nil), hour(1, 7, nil)], now: t0)
        XCTAssertNil(outlook.level)
        XCTAssertEqual(outlook.peak, 7)
    }

    func test_fixtureAktau_isCriticalThroughout() throws {
        let snapshot = try Fixture.snapshot()
        let aktau = try XCTUnwrap(snapshot.nodes.first { $0.code == "AKTAU" })
        let outlook = WindOutlook(hours: try XCTUnwrap(aktau.forecast), now: snapshot.generatedAt)
        XCTAssertEqual(outlook.level, .critical)
        XCTAssertNil(outlook.until)
    }
}
