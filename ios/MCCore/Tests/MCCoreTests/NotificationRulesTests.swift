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
        // было «Прибытие: Курык» часом раньше → стало «Отправление: Курык — погружен на паром»
        var old = s0412!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventKind = Coded(.arrived)
        old.lastEventNoteCode = nil
        old.lastEvent = "Прибытие: Курык"
        let notices = diff(old: [old], new: [s0412])
        XCTAssertEqual(notices.map(\.kind), [.event])
        XCTAssertTrue(notices[0].title.hasPrefix("MC-26-0412: Отправление: Курык"), notices[0].title)
    }

    /// Демо-сервер считает время событий от «сейчас»: у того же события оно растёт с каждым
    /// запросом. Это не новое событие — иначе баннер на каждый груз раз в минуту.
    func test_sameEventLaterTime_isSilent() {
        var old = s0398!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-60)
        XCTAssertTrue(diff(old: [old], new: [s0398]).filter { $0.kind == .event }.isEmpty)
    }

    func test_sameKindAndNode_newNote_notifies() {
        // тот же узел и вид, но новое примечание (например, «погружен на паром») — новость
        var old = s0412!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventNoteCode = nil
        old.lastEvent = "Отправление: Курык"
        XCTAssertEqual(diff(old: [old], new: [s0412]).map(\.kind), [.event])
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

    // MARK: ревью недель 3–4

    func test_delivered_noStormForDestination() {
        var delivered = s0398!
        delivered.state = Coded(.delivered)
        delivered.position.fromCode = "CONSTANTA"
        delivered.position.mode = nil
        let notices = diff(
            old: [delivered], new: [delivered], oldNodes: level("CONSTANTA", nil),
            newNodes: level("CONSTANTA", .critical))
        XCTAssertTrue(notices.isEmpty, notices.map(\.title).joined(separator: "; "))
    }

    func test_eventBackwards_isSilent() {
        var later = s0398!
        later.lastEventAt = later.lastEventAt?.addingTimeInterval(3600)
        // старое → новое во времени назад (сброс истории демо)
        XCTAssertTrue(diff(old: [later], new: [s0398]).filter { $0.kind == .event }.isEmpty)
    }

    func test_noPreviousSnapshot_noStorms() {
        XCTAssertTrue(diff(old: [s0398], new: [s0398], oldNodes: [], newNodes: level("AKTAU", .critical)).isEmpty)
    }

    func test_merge_onePerShipment_stormOnTop() {
        var old = s0398!
        old.delayHours -= 6
        old.queue?.p50Hours = 12
        let notices = diff(old: [old], new: [s0398], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        XCTAssertEqual(notices.count, 3)
        let merged = NotificationRules.merge(notices)
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged[0].kind, .storm)
        XCTAssertEqual(merged[0].title, "Шторм: Актау — вероятна остановка")
        XCTAssertTrue(merged[0].body.contains("в очереди в этом порту"), merged[0].body)
        XCTAssertTrue(merged[0].body.contains("2–3 дня"), merged[0].body)
        XCTAssertTrue(merged[0].body.contains("+18 ч"), merged[0].body)
    }

    func test_merge_keepsShipmentsApart() {
        // у обоих грузов прежнее событие — часом раньше и в другом узле
        func previous(_ s: Shipment) -> Shipment {
            var old = s
            old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
            old.lastEventNode = "PREV"
            old.lastEvent = "Прежнее событие"
            return old
        }
        let merged = NotificationRules.merge(diff(old: [previous(s0398), previous(s0412)], new: [s0398, s0412]))
        XCTAssertEqual(Set(merged.map(\.ref)), ["MC-26-0398", "MC-26-0412"])
    }

    // MARK: санкции — по состоянию и набору отправленных

    private func flagged() throws -> Shipment {
        try XCTUnwrap(try Fixture.snapshot().shipments.first { $0.ref == "MC-26-0431" })
    }

    private func sanctions(
        _ shipments: [Shipment], sent: Set<String> = [], settings: NotifySettings = .all, lang: Lang = .ru
    ) -> [AppNotice] {
        NotificationRules.sanctions(shipments, sent: sent, settings: settings, labels: Labels(lang: lang, nodes: nodes))
    }

    /// Ещё одно сильное совпадение у 0431: поз. 9, код 7210 (прил. XVII), происхождение RU.
    private func withExtraStrong(_ s: Shipment) throws -> Shipment {
        var s = s
        var extra = try XCTUnwrap(s.sanctions?.matches.first)
        extra.lineNo = 9
        extra.hsCode = "7210490000"
        extra.listCode = "7210"
        s.sanctions?.matches.insert(extra, at: 1)
        return s
    }

    func test_sanctions_flagged_notifies_withoutOldState() throws {
        let notices = sanctions([try flagged()])
        XCTAssertEqual(notices.map(\.kind), [.sanctions])
        XCTAssertEqual(notices[0].title, "MC-26-0431: возможна санкционка")
        XCTAssertTrue(notices[0].body.hasPrefix("По списку ЕС 833/2014 (прил. XVII): поз. 3"), notices[0].body)
        XCTAssertTrue(notices[0].body.hasSuffix("Проверьте вручную."), notices[0].body)
    }

    func test_sanctions_sentSet_blocksRepeat_withoutOldState() throws {
        let s = try flagged()
        let first = sanctions([s])
        XCTAssertEqual(first.count, 1)
        XCTAssertTrue(sanctions([s], sent: Set(first.map(\.id))).isEmpty)
    }

    func test_sanctions_newStrongMatch_newId() throws {
        let s = try flagged()
        let first = sanctions([s])
        let again = sanctions([try withExtraStrong(s)], sent: Set(first.map(\.id)))
        XCTAssertEqual(again.count, 1)
        XCTAssertNotEqual(again.first?.id, first.first?.id)
    }

    func test_sanctions_review_and_clear_silent() throws {
        XCTAssertEqual(s0412.sanctions?.status.known, .review)
        XCTAssertEqual(s0398.sanctions?.status.known, .clear)
        XCTAssertTrue(sanctions([s0412, s0398]).isEmpty)
    }

    func test_sanctions_missing_notifies() throws {
        var s = s0412!
        s.sanctions?.status = Coded(.missing)
        s.sanctions?.matches = []
        let notices = sanctions([s])
        XCTAssertEqual(notices.map(\.title), ["MC-26-0412: прошёл границу Казахстана без пакинг-листа"])
        XCTAssertEqual(notices.first?.body, "Проверить на санкции нельзя — запросите пакинг-лист до Актау.")
    }

    func test_sanctions_settingOff_silent() throws {
        var off = NotifySettings.all
        off.sanctions = false
        XCTAssertTrue(sanctions([try flagged()], settings: off).isEmpty)
    }

    func test_sanctions_one_notice_per_shipment() throws {
        let notices = sanctions([try withExtraStrong(try flagged())])
        XCTAssertEqual(notices.count, 1)
        XCTAssertTrue(notices[0].body.contains("и ещё 1"), notices[0].body)
    }

    func test_sanctions_english() throws {
        let notices = sanctions([try flagged()], lang: .en)
        XCTAssertEqual(notices.first?.title, "MC-26-0431: possible sanctioned goods")
        XCTAssertTrue(notices.first?.body.hasSuffix("Check manually.") == true, notices.first?.body ?? "")
    }

    func test_merge_sanctionsOnTopOfStorm() {
        let storm = AppNotice(id: "storm-x", kind: .storm, ref: "R", title: "Шторм", body: "b")
        let sanc = AppNotice(id: "sanctions-x", kind: .sanctions, ref: "R", title: "Санкции", body: "s")
        let merged = NotificationRules.merge([storm, sanc])
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged.first?.kind, .sanctions)
        XCTAssertEqual(merged.first?.title, "Санкции")
    }
}
