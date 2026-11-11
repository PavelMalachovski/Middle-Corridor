import Foundation
import XCTest

@testable import MCCore

final class AccountFormsTests: XCTestCase {
    private func me(_ memberships: [[String: Any]], admin: Bool = false) throws -> Me {
        let json: [String: Any] = [
            "id": 1, "email": "a@b.c", "name": NSNull(), "locale": "ru", "is_platform_admin": admin,
            "memberships": memberships,
        ]
        return try APIDate.makeDecoder().decode(Me.self, from: JSONSerialization.data(withJSONObject: json))
    }

    private func membership(_ org: Int, kind: String, role: String, nodes: [String] = []) -> [String: Any] {
        ["org_id": org, "org_name": "Org \(org)", "org_kind": kind, "role": role, "node_codes": nodes]
    }

    private func mine() throws -> [MyShipment] {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: "my_shipments", withExtension: "json", subdirectory: "Fixtures/account"))
        return try APIDate.makeDecoder().decode([MyShipment].self, from: Data(contentsOf: url))
    }

    private func segment(_ a: String, _ b: String, _ mode: String) throws -> RouteSegment {
        let json: [String: Any] = ["from_code": a, "to_code": b, "mode": mode, "coordinates": [[0.0, 0.0]]]
        return try APIDate.makeDecoder().decode(RouteSegment.self, from: JSONSerialization.data(withJSONObject: json))
    }

    // MARK: - Права

    func test_creatableOrgs_forwarderOwnerAdminOnly() throws {
        let user = try me([
            membership(1, kind: "forwarder", role: "owner"),
            membership(2, kind: "forwarder", role: "agent", nodes: ["AKTAU"]),
            membership(3, kind: "client", role: "owner"),
            membership(4, kind: "forwarder", role: "admin"),
        ])
        XCTAssertEqual(AccountAccess.creatableOrgs(user).map(\.orgId), [1, 4])
        XCTAssertEqual(AccountAccess.managedOrgs(user).map(\.orgId), [1, 3, 4])
        XCTAssertFalse(AccountAccess.canManageMembers(user, orgId: 2))
        XCTAssertTrue(AccountAccess.canManageMembers(user, orgId: 3))
    }

    func test_creatableOrgs_platformAdminAnyForwarder() throws {
        let user = try me([membership(5, kind: "forwarder", role: "viewer")], admin: true)
        XCTAssertEqual(AccountAccess.creatableOrgs(user).map(\.orgId), [5])
        XCTAssertTrue(AccountAccess.canManageMembers(user, orgId: 5))
        XCTAssertTrue(AccountAccess.creatableOrgs(nil).isEmpty)
    }

    // MARK: - Маршрут

    func test_presets_matchMockRoutes() {
        XCTAssertEqual(RoutePreset.europeToKazakhstan.codes.first, "MLADA_BOLESLAV")
        XCTAssertEqual(RoutePreset.europeToKazakhstan.codes.last, "KOSTANAY")
        XCTAssertEqual(RoutePreset.chinaToEurope.codes.first, "XIAN")
        XCTAssertEqual(RoutePreset.chinaToEurope.codes.last, "CONSTANTA")
        XCTAssertEqual(RoutePreset.chinaToEurope.codes.count, 14)
    }

    func test_routeGraph_neighboursBothDirectionsWithoutRepeats() throws {
        let graph = RouteGraph(segments: [
            try segment("AKTAU", "BAKU_ALAT", "sea"), try segment("BEINEU", "AKTAU", "rail"),
            try segment("BAKU_ALAT", "GANJA", "rail"),
        ])
        XCTAssertEqual(graph.nodes, ["AKTAU", "BAKU_ALAT", "BEINEU", "GANJA"])
        XCTAssertEqual(graph.nextChoices(after: []), ["AKTAU", "BAKU_ALAT", "BEINEU", "GANJA"])
        XCTAssertEqual(graph.nextChoices(after: ["AKTAU"]), ["BAKU_ALAT", "BEINEU"])
        XCTAssertEqual(graph.nextChoices(after: ["BEINEU", "AKTAU"]), ["BAKU_ALAT"])
        XCTAssertEqual(graph.mode("BAKU_ALAT", "AKTAU"), .sea)
        XCTAssertEqual(graph.mode("AKTAU", "BEINEU"), .rail)
        XCTAssertNil(graph.mode("AKTAU", "GANJA"))
        XCTAssertTrue(graph.isValid(["BEINEU", "AKTAU", "BAKU_ALAT", "GANJA"]))
        XCTAssertFalse(graph.isValid(["AKTAU"]))
        XCTAssertFalse(graph.isValid(["AKTAU", "GANJA"]))
        XCTAssertFalse(graph.isValid(["AKTAU", "BEINEU", "AKTAU"]))
    }

    func test_nextLegIsSea() throws {
        let graph = RouteGraph(segments: [
            try segment("AKTAU", "BAKU_ALAT", "sea"), try segment("BEINEU", "AKTAU", "rail"),
        ])
        let route = ["BEINEU", "AKTAU", "BAKU_ALAT"]
        XCTAssertTrue(graph.nextLegIsSea(from: "AKTAU", route: route))
        XCTAssertFalse(graph.nextLegIsSea(from: "BEINEU", route: route))
        XCTAssertFalse(graph.nextLegIsSea(from: "BAKU_ALAT", route: route))  // конец маршрута
        XCTAssertFalse(graph.nextLegIsSea(from: "POTI", route: route))
    }

    func test_lockedPrefix_upToLastReachedCheckpoint() throws {
        let shipment = try XCTUnwrap(mine().first)
        // фикстура: AKTAU — current (9-й узел), дальше planned
        XCTAssertEqual(RouteEdit.lockedCount(shipment.shipment), 9)
        XCTAssertEqual(RouteEdit.route(shipment.shipment).count, 11)
    }

    // MARK: - Событие

    func test_eventNodeChoices_intersectRouteInRouteOrder() throws {
        var shipment = try XCTUnwrap(mine().first)
        XCTAssertEqual(EventDraft.nodeChoices(shipment).count, 11)
        let json = try JSONSerialization.jsonObject(with: APIDate.makeEncoder().encode(shipment)) as? [String: Any]
        var dict = try XCTUnwrap(json)
        dict["event_nodes"] = ["KOSTANAY", "AKTAU", "ZZZ"]
        shipment = try APIDate.makeDecoder().decode(MyShipment.self, from: JSONSerialization.data(withJSONObject: dict))
        XCTAssertEqual(EventDraft.nodeChoices(shipment), ["AKTAU", "KOSTANAY"])
    }

    func test_eventDraft_heldNeedsReasonAndOtherNeedsNote() {
        var draft = EventDraft(node: "AKTAU")
        draft.kind = .held
        XCTAssertFalse(draft.canSubmit)  // причина не выбрана
        draft.hold = .weatherBan
        XCTAssertTrue(draft.canSubmit)
        let input = draft.input(vesselAllowed: false)
        XCTAssertEqual(input.holdCode, "weather_ban")
        XCTAssertNil(input.occurredAt)  // время не трогали — «сейчас» ставит сервер
        draft.hold = .other
        XCTAssertFalse(draft.canSubmit)
        draft.note = "  Ремонт крана "
        XCTAssertTrue(draft.canSubmit)
        let other = draft.input(vesselAllowed: false)
        XCTAssertEqual(other.holdCode, "other")  // сервер требует код и у «другой причины»
        XCTAssertEqual(other.note, "Ремонт крана")
    }

    func test_eventDraft_holdOnlyForHeldVesselOnlyWhenAllowed() {
        var draft = EventDraft(node: "AKTAU")
        draft.kind = .departed
        draft.hold = .customsWait
        draft.vessel = " Barda "
        draft.note = "   "
        let at = Date(timeIntervalSince1970: 1_800_000_000)
        draft.occurredAt = at
        XCTAssertTrue(draft.canSubmit)
        let sea = draft.input(vesselAllowed: true)
        XCTAssertNil(sea.holdCode)
        XCTAssertNil(sea.note)
        XCTAssertEqual(sea.vessel, "Barda")
        XCTAssertEqual(sea.occurredAt, at)
        XCTAssertNil(draft.input(vesselAllowed: false).vessel)
    }

    func test_eventDraft_limits() {
        var draft = EventDraft(node: "AKTAU")
        draft.note = String(repeating: "a", count: EventDraft.noteMax + 1)
        XCTAssertFalse(draft.canSubmit)
        draft.note = ""
        draft.vessel = String(repeating: "v", count: EventDraft.vesselMax + 1)
        XCTAssertFalse(draft.canSubmit)
    }

    // MARK: - Ошибки

    func test_errorKeys() {
        for code in [
            "node_not_allowed", "in_future", "out_of_order", "backwards", "hold_code_required", "bad_hold_code",
            "no_open_hold", "bad_supersedes", "note_too_long", "vessel_too_long", "archived", "bad_container",
            "bad_route", "route_passed_part", "unknown_node", "nodes_for_agent_only", "last_owner",
        ] {
            XCTAssertEqual(AccountErrorKey.key(.rejected(code)), "account.error.\(code)")
        }
        XCTAssertEqual(AccountErrorKey.key(.rejected("something_new")), "account.error.generic")
        XCTAssertEqual(AccountErrorKey.key(.rejected("invalid")), "account.error.generic")
        XCTAssertEqual(AccountErrorKey.key(.offline), "settings.fail.offline")
        XCTAssertEqual(AccountErrorKey.key(.notFound), "account.error.notFound")
        XCTAssertEqual(AccountErrorKey.key(.unauthorized), "account.expired")
        XCTAssertEqual(AccountErrorKey.key(.http(500)), "account.error.generic")
    }

    func test_pushTokenHex() {
        XCTAssertEqual(PushToken.hex(Data([0x00, 0xAB, 0x10, 0xFF])), "00ab10ff")
    }
}
