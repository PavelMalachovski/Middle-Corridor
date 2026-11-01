import Foundation
import XCTest
@testable import MCCore

final class NotificationRulesTests: XCTestCase {
    private var nodes: [NodeStatus] = []
    private var s0398: Shipment!
    private var s0412: Shipment!

    override func setUpWithError() throws {
        nodes = try Fixture.snapshot().nodes
        s0398 = try Fixture.shipment("MC-26-0398")
        s0412 = try Fixture.shipment("MC-26-0412")
    }

    private func level(_ code: String, _ level: AlertLevel?) -> [NodeStatus] {
        nodes.map { node in
            var copy = node
            if node.code == code { copy.alertLevel = level.map { Coded($0) } }
            return copy
        }
    }

    private func diff(
        old: [Shipment], new: [Shipment], oldNodes: [NodeStatus]? = nil, newNodes: [NodeStatus]? = nil,
        settings: NotifySettings = .all, lang: Lang = .ru
    ) -> [AppNotice] {
        let newNodes = newNodes ?? nodes
        return NotificationRules.diff(
            old: Dictionary(uniqueKeysWithValues: old.map { ($0.ref, $0) }),
            new: Dictionary(uniqueKeysWithValues: new.map { ($0.ref, $0) }),
            oldNodes: oldNodes ?? nodes, newNodes: newNodes,
            settings: settings, labels: Labels(lang: lang, nodes: newNodes))
    }

    func test_firstLoad_isSilent() {
        XCTAssertTrue(diff(old: [], new: [s0398, s0412], oldNodes: level("AKTAU", .warning)).isEmpty)
    }

    func test_nothingChanged_isSilent() {
        XCTAssertTrue(diff(old: [s0398, s0412], new: [s0398, s0412]).isEmpty)
    }

    func test_eventChanged_notifies() throws {
        var old = s0412!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        let notices = diff(old: [old], new: [s0412])
        XCTAssertEqual(notices.map(\.kind), [.event])
        XCTAssertTrue(notices[0].title.hasPrefix("MC-26-0412: Отправление: Курык"), notices[0].title)
    }

    func test_delayGrew3h_notifies() {
        var old = s0398!
        old.delayHours = s0398.delayHours - 3
        let notices = diff(old: [old], new: [s0398])
        XCTAssertEqual(notices.map(\.kind), [.delay])
        XCTAssertTrue(notices[0].title.contains("+18 ч"), notices[0].title)
    }

    func test_delayGrew2h_isSilent() {
        var old = s0398!
        old.delayHours = s0398.delayHours - 2
        XCTAssertTrue(diff(old: [old], new: [s0398]).isEmpty)
    }

    func test_stormEscalation_warningToCritical_notifies() {
        let notices = diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        XCTAssertEqual(notices.map(\.kind), [.storm])
        XCTAssertEqual(notices[0].title, "Шторм: Актау — вероятна остановка")
        XCTAssertTrue(notices[0].body.contains("в очереди"), notices[0].body)
    }

    func test_storm_criticalToCritical_isSilent() {
        XCTAssertTrue(diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", .critical), newNodes: level("AKTAU", .critical)).isEmpty)
    }

    func test_storm_downgrade_isSilent() {
        XCTAssertTrue(diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", .critical), newNodes: level("AKTAU", .warning)).isEmpty)
    }

    func test_storm_watchIsSilent() {
        XCTAssertTrue(diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", nil), newNodes: level("AKTAU", .watch)).isEmpty)
    }

    func test_stormAhead_notWaitingThere() {
        let notices = diff(old: [s0412], new: [s0412], oldNodes: level("BAKU_ALAT", nil), newNodes: level("BAKU_ALAT", .warning))
        XCTAssertEqual(notices.map(\.kind), [.storm])
        XCTAssertTrue(notices[0].title.contains("Баку (Алят)"), notices[0].title)
        XCTAssertTrue(notices[0].body.contains("на пути"), notices[0].body)
    }

    func test_stormBehind_isSilent() {
        // Курык 0412 уже прошёл
        XCTAssertTrue(diff(old: [s0412], new: [s0412], oldNodes: level("KURYK", nil), newNodes: level("KURYK", .critical)).isEmpty)
    }

    func test_queueShift12h_notifies() throws {
        var old = s0398!
        old.queue?.p50Hours = 48
        let notices = diff(old: [old], new: [s0398])
        XCTAssertEqual(notices.map(\.kind), [.queue])
        XCTAssertEqual(notices[0].title, "Выход из очереди MC-26-0398: 2–3 дня")
        XCTAssertEqual(notices[0].body, "в плохом сценарии — до 5 дней")
    }

    func test_queueShift6h_isSilent() {
        var old = s0398!
        old.queue?.p50Hours = 54
        XCTAssertTrue(diff(old: [old], new: [s0398]).isEmpty)
    }

    func test_queueAppeared_notifies() {
        var old = s0398!
        old.queue = nil
        XCTAssertEqual(diff(old: [old], new: [s0398]).map(\.kind), [.queue])
    }

    func test_settingsOff_filters() {
        var old = s0398!
        old.delayHours -= 5
        old.queue = nil
        var settings = NotifySettings.all
        settings.delay = false
        XCTAssertEqual(diff(old: [old], new: [s0398], settings: settings).map(\.kind), [.queue])
    }

    func test_removedRef_isSilent() {
        var old = s0412!
        old.lastEventAt = nil
        XCTAssertTrue(diff(old: [old], new: []).isEmpty)
    }

    func test_english_texts() {
        let notices = diff(
            old: [s0398], new: [s0398], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical), lang: .en)
        XCTAssertEqual(notices.first?.title, "Storm: Aktau — stoppage likely")
        XCTAssertTrue(notices.first?.body.contains("queued") ?? false)
    }

    func test_ids_stable() {
        let a = diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        let b = diff(old: [s0398], new: [s0398], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        XCTAssertEqual(a.map(\.id), b.map(\.id))
        XCTAssertEqual(a.first?.id, "storm-MC-26-0398-AKTAU-critical")
    }
}
