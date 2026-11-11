import Foundation
import XCTest
@testable import MCCore

final class NotificationRulesTests: XCTestCase {
    private var nodes: [NodeStatus] = []
    /// 0501 на такте «шторм»: ждёт в Аляте (очередь, +30 ч), запрет на швартовку в Актау
    private var s0501: Shipment!
    /// 0431 в пути по рельсам без задержки
    private var s0431: Shipment!
    /// публичный 0501 на пароме «Shahdag»: Алят → Актау
    private var ferry: Shipment!

    override func setUpWithError() throws {
        nodes = try Fixture.snapshot().nodes
        s0501 = try Fixture.shipment("MC-26-0501")
        s0431 = try Fixture.shipment("MC-26-0431")
        ferry = try Fixture.shipment("MC-26-0501_ferry")
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
        XCTAssertTrue(diff(old: [], new: [s0501, s0431], oldNodes: level("BAKU_ALAT", .warning)).isEmpty)
    }

    func test_nothingChanged_isSilent() {
        XCTAssertTrue(diff(old: [s0501, s0431], new: [s0501, s0431]).isEmpty)
    }

    func test_eventChanged_notifies() throws {
        // было «Прибытие: Баку (Алят)» часом раньше → стало «Отправление: Баку (Алят) — погружен на паром»
        var old = ferry!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventKind = Coded(.arrived)
        old.lastEventNoteCode = nil
        old.lastEvent = "Прибытие: Баку (Алят)"
        let notices = diff(old: [old], new: [ferry])
        XCTAssertEqual(notices.map(\.kind), [.event])
        XCTAssertTrue(notices[0].title.hasPrefix("MC-26-0501: Отправление: Баку (Алят)"), notices[0].title)
    }

    /// Демо-сервер считает время событий от «сейчас»: у того же события оно растёт с каждым
    /// запросом. Это не новое событие — иначе баннер на каждый груз раз в минуту.
    func test_sameEventLaterTime_isSilent() {
        var old = s0501!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-60)
        XCTAssertTrue(diff(old: [old], new: [s0501]).filter { $0.kind == .event }.isEmpty)
    }

    func test_sameKindAndNode_newNote_notifies() {
        // тот же узел и вид, но новое примечание (например, «погружен на паром») — новость
        var old = ferry!
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventNoteCode = nil
        old.lastEvent = "Отправление: Баку (Алят)"
        XCTAssertEqual(diff(old: [old], new: [ferry]).map(\.kind), [.event])
    }

    func test_delayGrew3h_notifies() {
        var old = s0501!
        old.delayHours = s0501.delayHours - 3
        let notices = diff(old: [old], new: [s0501])
        XCTAssertEqual(notices.map(\.kind), [.delay])
        XCTAssertTrue(notices[0].title.contains("+30 ч"), notices[0].title)
    }

    func test_delayGrew2h_isSilent() {
        var old = s0501!
        old.delayHours = s0501.delayHours - 2
        XCTAssertTrue(diff(old: [old], new: [s0501]).isEmpty)
    }

    func test_stormEscalation_warningToCritical_notifies() {
        let notices = diff(old: [s0501], new: [s0501], oldNodes: level("BAKU_ALAT", .warning), newNodes: level("BAKU_ALAT", .critical))
        XCTAssertEqual(notices.map(\.kind), [.storm])
        XCTAssertEqual(notices[0].title, "Шторм: Баку (Алят) — вероятна остановка")
        XCTAssertTrue(notices[0].body.contains("в очереди"), notices[0].body)
    }

    func test_storm_criticalToCritical_isSilent() {
        XCTAssertTrue(diff(old: [s0501], new: [s0501], oldNodes: level("BAKU_ALAT", .critical), newNodes: level("BAKU_ALAT", .critical)).isEmpty)
    }

    func test_storm_downgrade_isSilent() {
        XCTAssertTrue(diff(old: [s0501], new: [s0501], oldNodes: level("BAKU_ALAT", .critical), newNodes: level("BAKU_ALAT", .warning)).isEmpty)
    }

    func test_storm_watchIsSilent() {
        XCTAssertTrue(diff(old: [s0501], new: [s0501], oldNodes: level("BAKU_ALAT", nil), newNodes: level("BAKU_ALAT", .watch)).isEmpty)
    }

    func test_stormAhead_notWaitingThere() {
        // история демо: 0501 ждёт в Аляте, шторм — в Актау (следующий порт)
        let notices = diff(old: [s0501], new: [s0501], oldNodes: level("AKTAU", nil), newNodes: level("AKTAU", .warning))
        XCTAssertEqual(notices.map(\.kind), [.storm])
        XCTAssertTrue(notices[0].title.contains("Актау"), notices[0].title)
        XCTAssertTrue(notices[0].body.contains("на пути"), notices[0].body)
    }

    func test_stormBehind_isSilent() {
        // Поти 0501 уже прошёл
        XCTAssertTrue(diff(old: [s0501], new: [s0501], oldNodes: level("POTI", nil), newNodes: level("POTI", .critical)).isEmpty)
    }

    func test_queueShift12h_notifies() throws {
        var old = s0501!
        old.queue?.p50Hours = 48
        let notices = diff(old: [old], new: [s0501])
        XCTAssertEqual(notices.map(\.kind), [.queue])
        XCTAssertEqual(notices[0].title, "Выход из очереди MC-26-0501: 2–3 дня")
        XCTAssertEqual(notices[0].body, "в плохом сценарии — до 5 дней")
    }

    func test_queueShift6h_isSilent() {
        var old = s0501!
        old.queue?.p50Hours = 54
        XCTAssertTrue(diff(old: [old], new: [s0501]).isEmpty)
    }

    func test_queueAppeared_notifies() {
        var old = s0501!
        old.queue = nil
        XCTAssertEqual(diff(old: [old], new: [s0501]).map(\.kind), [.queue])
    }

    func test_settingsOff_filters() {
        var old = s0501!
        old.delayHours -= 5
        old.queue = nil
        var settings = NotifySettings.all
        settings.delay = false
        XCTAssertEqual(diff(old: [old], new: [s0501], settings: settings).map(\.kind), [.queue])
    }

    func test_removedRef_isSilent() {
        var old = s0431!
        old.lastEventAt = nil
        XCTAssertTrue(diff(old: [old], new: []).isEmpty)
    }

    func test_english_texts() {
        let notices = diff(
            old: [s0501], new: [s0501], oldNodes: level("BAKU_ALAT", .warning), newNodes: level("BAKU_ALAT", .critical), lang: .en)
        XCTAssertEqual(notices.first?.title, "Storm: Baku (Alat) — stoppage likely")
        XCTAssertTrue(notices.first?.body.contains("queued") ?? false)
    }

    func test_ids_stable() {
        let a = diff(old: [s0501], new: [s0501], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        let b = diff(old: [s0501], new: [s0501], oldNodes: level("AKTAU", .warning), newNodes: level("AKTAU", .critical))
        XCTAssertEqual(a.map(\.id), b.map(\.id))
        XCTAssertEqual(a.first?.id, "storm-MC-26-0501-AKTAU-critical")
    }

    // MARK: ревью недель 3–4

    func test_delivered_noStormForDestination() {
        // 0431 доставлен в Констанцу (порт, ветер отслеживается) — шторм там его уже не касается
        var delivered = s0431!
        delivered.state = Coded(.delivered)
        delivered.position.fromCode = "CONSTANTA"
        delivered.position.mode = nil
        let notices = diff(
            old: [delivered], new: [delivered], oldNodes: level("CONSTANTA", nil),
            newNodes: level("CONSTANTA", .critical))
        XCTAssertTrue(notices.isEmpty, notices.map(\.title).joined(separator: "; "))
    }

    func test_eventBackwards_isSilent() {
        var later = s0501!
        later.lastEventAt = later.lastEventAt?.addingTimeInterval(3600)
        // старое → новое во времени назад (сброс истории демо)
        XCTAssertTrue(diff(old: [later], new: [s0501]).filter { $0.kind == .event }.isEmpty)
    }

    func test_noPreviousSnapshot_noStorms() {
        XCTAssertTrue(diff(old: [s0501], new: [s0501], oldNodes: [], newNodes: level("AKTAU", .critical)).isEmpty)
    }

    func test_merge_onePerShipment_stormOnTop() {
        var old = s0501!
        old.delayHours -= 6
        old.queue?.p50Hours = 12
        let notices = diff(old: [old], new: [s0501], oldNodes: level("BAKU_ALAT", .warning), newNodes: level("BAKU_ALAT", .critical))
        XCTAssertEqual(notices.count, 3)
        let merged = NotificationRules.merge(notices)
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged[0].kind, .storm)
        XCTAssertEqual(merged[0].title, "Шторм: Баку (Алят) — вероятна остановка")
        XCTAssertTrue(merged[0].body.contains("в очереди в этом порту"), merged[0].body)
        XCTAssertTrue(merged[0].body.contains("2–3 дня"), merged[0].body)
        XCTAssertTrue(merged[0].body.contains("+30 ч"), merged[0].body)
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
        let merged = NotificationRules.merge(diff(old: [previous(s0501), previous(s0431)], new: [s0501, s0431]))
        XCTAssertEqual(Set(merged.map(\.ref)), ["MC-26-0501", "MC-26-0431"])
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
        let review = try Fixture.review()
        XCTAssertEqual(review.sanctions?.status.known, .review)
        XCTAssertEqual(s0501.sanctions?.status.known, .clear)
        XCTAssertTrue(sanctions([review, s0501]).isEmpty)
    }

    func test_sanctions_missing_notifies() throws {
        var s = s0431!
        s.sanctions?.status = Coded(.missing)
        s.sanctions?.matches = []
        let notices = sanctions([s])
        XCTAssertEqual(notices.map(\.title), ["MC-26-0431: прошёл границу Казахстана без пакинг-листа"])
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
