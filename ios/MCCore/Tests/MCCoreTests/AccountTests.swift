import Foundation
import XCTest
@testable import MCCore

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

private func accountData(_ name: String) throws -> Data {
    let url = try XCTUnwrap(
        Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures/account"),
        "нет фикстуры account/\(name).json")
    return try Data(contentsOf: url)
}

final class AccountModelsTests: XCTestCase {
    func test_me_decodes() throws {
        let me = try APIDate.makeDecoder().decode(Me.self, from: accountData("me"))
        XCTAssertEqual(me.email, "owner@example.com")
        XCTAssertFalse(me.isPlatformAdmin)
        XCTAssertEqual(me.memberships.count, 1)
        XCTAssertEqual(me.memberships[0].role.known, .owner)
        XCTAssertEqual(me.memberships[0].orgKind.known, .forwarder)
        XCTAssertEqual(me.memberships[0].orgName, "Demo Forwarder")
    }

    func test_myShipments_decode() throws {
        let list = try APIDate.makeDecoder().decode([MyShipment].self, from: accountData("my_shipments"))
        let mine = try XCTUnwrap(list.first)
        XCTAssertEqual(mine.containerNo, "CSQU3054383")
        XCTAssertTrue(mine.canManage)
        XCTAssertEqual(mine.id, mine.shipment.ref)
        XCTAssertTrue(mine.eventNodes.contains("AKTAU"))
        XCTAssertEqual(mine.shipment.lastEventKind?.known, .arrived)
        XCTAssertEqual(mine.shipment.holdCode, "weather_ban")
    }

    func test_events_decode_naiveDatesAreUTC() throws {
        let events = try APIDate.makeDecoder().decode([CheckpointEventRecord].self, from: accountData("events"))
        XCTAssertEqual(events.map(\.kind.known), [.departed, .arrived, .held])
        XCTAssertEqual(events[2].holdCode, "weather_ban")
        XCTAssertEqual(events[2].note, "Шторм")
        XCTAssertFalse(events[2].superseded)
        XCTAssertEqual(events[0].occurredAt, APIDate.parse("2027-03-01T09:00:00Z"))
    }

    func test_unknownKind_doesNotBreakDecoding() throws {
        let json = #"""
            {"id":1,"kind":"teleported","node_code":"AKTAU","occurred_at":"2027-03-01T09:00:00",
             "hold_code":null,"note":null,"vessel":null,"source":"manual","created_by":null,
             "supersedes_id":null,"created_at":"2027-03-01T09:00:00","superseded":false}
            """#
        let e = try APIDate.makeDecoder().decode(CheckpointEventRecord.self, from: Data(json.utf8))
        XCTAssertNil(e.kind.known)
        XCTAssertEqual(e.kind.raw, "teleported")
    }

    private func object(_ value: some Encodable) throws -> [String: Any] {
        let data = try APIDate.makeEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func test_eventInput_encodesSnakeCaseAndOmitsNil() throws {
        let input = CheckpointEventInput(
            kind: .held, nodeCode: "AKTAU", occurredAt: APIDate.parse("2027-03-08T12:00:00Z"),
            holdCode: "weather_ban", note: "Шторм")
        let json = try object(input)
        XCTAssertEqual(json["kind"] as? String, "held")
        XCTAssertEqual(json["node_code"] as? String, "AKTAU")
        XCTAssertEqual(json["occurred_at"] as? String, "2027-03-08T12:00:00Z")
        XCTAssertEqual(json["hold_code"] as? String, "weather_ban")
        XCTAssertNil(json["vessel"])
        XCTAssertNil(json["supersedes_id"])
    }

    func test_newShipment_encodes() throws {
        let new = NewShipment(
            orgId: 1, containerNo: "CSQU3054383", route: ["AKTAU", "KOSTANAY"],
            plannedDepartureAt: APIDate.parse("2027-03-01T08:00:00Z")!, cargo: "Запчасти")
        let json = try object(new)
        XCTAssertEqual(json["org_id"] as? Int, 1)
        XCTAssertEqual(json["container_no"] as? String, "CSQU3054383")
        XCTAssertEqual(json["planned_departure_at"] as? String, "2027-03-01T08:00:00Z")
        XCTAssertEqual(json["route"] as? [String], ["AKTAU", "KOSTANAY"])
        XCTAssertNil(json["container_type"])
    }

    func test_patch_onlySetFields_andExplicitNull() throws {
        XCTAssertTrue(try object(ShipmentPatch()).isEmpty)
        let json = try object(ShipmentPatch(containerNo: "CSQU3054383", cargo: .some(nil), cargoEn: "parts"))
        XCTAssertEqual(json["container_no"] as? String, "CSQU3054383")
        XCTAssertTrue(json["cargo"] is NSNull)
        XCTAssertEqual(json["cargo_en"] as? String, "parts")
        XCTAssertNil(json["container_type"])
        XCTAssertNil(json["route"])
    }

    /// Сервер принимает `other` кодом (HOLD_CODES), без кода `held` отклоняется.
    func test_holdCode_rawValuesMatchServer() {
        XCTAssertEqual(HoldCode.allCases.map(\.rawValue), ["weather_ban", "customs_wait", "ferry_loading_wait", "other"])
    }
}

final class ContainerNumberTests: XCTestCase {
    func test_iso6346() {
        XCTAssertTrue(ContainerNumber.isValid("CSQU3054383"))
        XCTAssertFalse(ContainerNumber.isValid("CSQU3054384"))
        XCTAssertFalse(ContainerNumber.isValid("CSQU305438"))
        XCTAssertFalse(ContainerNumber.isValid("1SQU3054383"))
        XCTAssertTrue(ContainerNumber.isValid(" csqu 305438 3 "))
        XCTAssertFalse(ContainerNumber.isValid("CSQU\u{0663}054383"))  // арабско-индийская «3»
        XCTAssertFalse(ContainerNumber.isValid(""))
    }

    func test_normalize() {
        XCTAssertEqual(ContainerNumber.normalize(" csqu 305438 3 "), "CSQU3054383")
    }
}

final class TokenStoreTests: XCTestCase {
    func test_inMemory() {
        let store = InMemoryTokenStore()
        XCTAssertNil(store.load())
        store.save("abc")
        XCTAssertEqual(store.load(), "abc")
        store.save(nil)
        XCTAssertNil(store.load())
    }
}

final class AccountAPITests: XCTestCase {
    private let tokens = InMemoryTokenStore(token: "tok-123")

    private func api(_ tokens: (any TokenStore)? = nil) -> HTTPAccountAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        return HTTPAccountAPI(
            baseURL: URL(string: "http://localhost:8000")!, tokens: tokens ?? self.tokens,
            session: URLSession(configuration: config))
    }

    override func tearDown() {
        StubProtocol.handler = nil
        StubProtocol.lastPath = nil
    }

    func test_sendsBearerAndPath() async throws {
        let body = try accountData("me")
        nonisolated(unsafe) var seen: URLRequest?
        StubProtocol.handler = { request in
            seen = request
            return (200, body)
        }
        let me = try await api().me()
        XCTAssertEqual(me.id, 1)
        XCTAssertEqual(seen?.value(forHTTPHeaderField: "Authorization"), "Bearer tok-123")
        XCTAssertEqual(seen?.httpMethod, "GET")
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/me")
    }

    func test_noToken_throwsUnauthorizedWithoutRequest() async {
        nonisolated(unsafe) var called = false
        StubProtocol.handler = { _ in
            called = true
            return (200, Data())
        }
        do {
            _ = try await api(InMemoryTokenStore()).me()
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }
        XCTAssertFalse(called)
    }

    func test_401_erasesToken() async {
        StubProtocol.handler = { _ in (401, Data(#"{"detail":"unauthorized"}"#.utf8)) }
        do {
            _ = try await api().myShipments()
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }
        XCTAssertNil(tokens.load())
    }

    func test_422_code_andSchemaError() async {
        StubProtocol.handler = { _ in (422, Data(#"{"detail":"node_not_allowed"}"#.utf8)) }
        let event = CheckpointEventInput(kind: .arrived, nodeCode: "AKTAU")
        do {
            _ = try await api().addEvent(ref: "MC-27-0001", event)
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .rejected("node_not_allowed"))
        }
        StubProtocol.handler = { _ in
            (422, Data(#"{"detail":[{"loc":["body","kind"],"msg":"bad","type":"enum"}]}"#.utf8))
        }
        do {
            _ = try await api().addEvent(ref: "MC-27-0001", event)
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .rejected("invalid"))
        }
        XCTAssertEqual(tokens.load(), "tok-123")  // 422 сессию не рвёт
    }

    func test_404_and_413() async {
        StubProtocol.handler = { _ in (404, Data(#"{"detail":"not_found"}"#.utf8)) }
        do {
            _ = try await api().events(ref: "MC-27-9999")
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .notFound)
        }
        StubProtocol.handler = { _ in (413, Data()) }
        do {
            _ = try await api().myShipments()
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .http(413))
        }
    }

    func test_verify_savesToken_noBearer() async throws {
        let me = try String(decoding: accountData("me"), as: UTF8.self)
        let body = Data(#"{"token":"new-token","me":\#(me)}"#.utf8)
        nonisolated(unsafe) var auth: String?
        StubProtocol.handler = { request in
            auth = request.value(forHTTPHeaderField: "Authorization")
            return (200, body)
        }
        let store = InMemoryTokenStore()
        let result = try await api(store).verify(email: "owner@example.com", code: "123456", deviceName: "iPhone")
        XCTAssertEqual(result.token, "new-token")
        XCTAssertEqual(store.load(), "new-token")
        XCTAssertNil(auth)
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/auth/verify")
    }

    func test_verify_wrongCode_keepsExistingToken() async {
        StubProtocol.handler = { _ in (401, Data(#"{"detail":"invalid_code"}"#.utf8)) }
        do {
            _ = try await api().verify(email: "a@example.com", code: "000000", deviceName: "")
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }
        XCTAssertEqual(tokens.load(), "tok-123")
    }

    func test_requestCode_202_noBearer() async throws {
        nonisolated(unsafe) var auth: String?
        StubProtocol.handler = { request in
            auth = request.value(forHTTPHeaderField: "Authorization")
            return (202, Data(#"{"status":"sent"}"#.utf8))
        }
        try await api(InMemoryTokenStore()).requestCode(email: "a@example.com")
        XCTAssertNil(auth)
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/auth/code")
    }

    func test_logout_erasesTokenEvenWhenOffline() async {
        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        do {
            try await api().logout(apnsToken: nil)
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .offline)
        }
        XCTAssertNil(tokens.load())
    }

    func test_logout_204() async throws {
        StubProtocol.handler = { _ in (204, Data()) }
        try await api().logout(apnsToken: nil)
        XCTAssertNil(tokens.load())
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/auth/logout")
    }

    func test_logout_sendsDeviceTokenOrNoBody() async throws {
        nonisolated(unsafe) var bodies: [String?] = []
        StubProtocol.handler = { request in
            var data = request.httpBody
            if data == nil, let stream = request.httpBodyStream {
                stream.open()
                defer { stream.close() }
                var collected = Data()
                var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let n = stream.read(&buffer, maxLength: buffer.count)
                    if n <= 0 { break }
                    collected.append(buffer, count: n)
                }
                data = collected
            }
            bodies.append(data.flatMap { String(data: $0, encoding: .utf8) })
            return (204, Data())
        }
        try await api().logout(apnsToken: "abcd")
        tokens.save("tok-123")  // выход стёр токен
        try await api().logout(apnsToken: nil)
        XCTAssertEqual(bodies.count, 2)
        guard bodies.count == 2 else { return }
        XCTAssertEqual(bodies[0], #"{"apns_token":"abcd"}"#)
        XCTAssertTrue(bodies[1] == nil || bodies[1] == "")
    }

    func test_voidEndpoints_methodsAndPaths() async throws {
        nonisolated(unsafe) var seen: [String] = []
        StubProtocol.handler = { request in
            seen.append("\(request.httpMethod ?? "") \(request.url?.path ?? "")")
            return (204, Data())
        }
        let api = api()
        try await api.share(ref: "MC-27-0001", orgId: 2)
        try await api.archive(ref: "MC-27-0001")
        try await api.revoke(orgId: 1, userId: 7)
        try await api.registerDevice(apnsToken: "aa", environment: "sandbox")
        XCTAssertEqual(
            seen,
            [
                "POST /api/v1/my/shipments/MC-27-0001/share",
                "POST /api/v1/my/shipments/MC-27-0001/archive",
                "DELETE /api/v1/orgs/1/members/7",
                "POST /api/v1/me/devices",
            ])
    }

    func test_listEndpoints_decode() async throws {
        let events = try accountData("events")
        StubProtocol.handler = { _ in (200, events) }
        let list = try await api().events(ref: "MC-27-0001")
        XCTAssertEqual(list.count, 3)
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/my/shipments/MC-27-0001/events")

        StubProtocol.handler = { _ in (201, Data(#"{"invitation_id":5,"mail":"failed"}"#.utf8)) }
        let invitation = try await api().invite(orgId: 1, email: "x@example.com", role: .agent, nodeCodes: ["AKTAU"])
        XCTAssertEqual(invitation.invitationId, 5)
        XCTAssertFalse(invitation.mailSent)

        StubProtocol.handler = { _ in (200, Data(#"[{"id":3,"name":"Client","kind":"client"}]"#.utf8)) }
        let clients = try await api().clients(orgId: 1)
        XCTAssertEqual(clients.first?.kind.known, .client)

        StubProtocol.handler = { _ in
            (200, Data(#"[{"user_id":2,"email":"a@example.com","name":null,"role":"agent","node_codes":["AKTAU"]}]"#.utf8))
        }
        let members = try await api().members(orgId: 1)
        XCTAssertEqual(members.first?.role.known, .agent)
    }
}

final class AccountLabelsAndRulesTests: XCTestCase {
    func test_labels_heldAndReleased() throws {
        let nodes = try Fixture.snapshot().nodes
        let ru = Labels(lang: .ru, nodes: nodes)
        let en = Labels(lang: .en, nodes: nodes)
        XCTAssertTrue(ru.checkpointEvent(.held, node: "AKTAU").hasPrefix("Стоянка: "))
        XCTAssertTrue(ru.checkpointEvent(.released, node: "AKTAU").hasPrefix("Стоянка снята: "))
        XCTAssertTrue(en.checkpointEvent(.held, node: "AKTAU").hasPrefix("Held: "))
        XCTAssertEqual(en.holdChoice(.other), "Other reason")
        XCTAssertEqual(ru.holdChoice(.weatherBan), "Погодный запрет")
        for lang in Lang.allCases {
            let labels = Labels(lang: lang, nodes: nodes)
            for code in HoldCode.allCases {
                XCTAssertNotEqual(labels.holdChoice(code), "hold.choice.\(code.rawValue)", "нет подписи")
            }
        }
    }

    func test_pushManagedRefs_skipsDiff_emptyKeepsBehaviour() throws {
        let nodes = try Fixture.snapshot().nodes
        let ferry = try Fixture.shipment("MC-26-0501_ferry")
        var old = ferry
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventKind = Coded(.arrived)
        old.lastEventNoteCode = nil
        old.lastEvent = "Прибытие: Баку (Алят)"
        func run(_ managed: Set<String>) -> [AppNotice] {
            NotificationRules.diff(
                old: [old.ref: old], new: [ferry.ref: ferry], oldNodes: nodes, newNodes: nodes,
                settings: .all, labels: Labels(lang: .ru, nodes: nodes), pushManagedRefs: managed)
        }
        XCTAssertEqual(run([]).map(\.kind), [.event])
        XCTAssertTrue(run([ferry.ref]).isEmpty)
        XCTAssertEqual(run(["MC-OTHER"]).map(\.kind), [.event])
    }
}

final class AccountReviewFixesTests: XCTestCase {
    override func tearDown() { StubProtocol.handler = nil }

    func test_pushManaged_stillGetsDelayNotice_notEvent() throws {
        let nodes = try Fixture.snapshot().nodes
        let s = try Fixture.shipment("MC-26-0501")
        var old = s
        old.delayHours = 0
        old.lastEventAt = old.lastEventAt?.addingTimeInterval(-3600)
        old.lastEventKind = Coded(.departed)
        old.lastEvent = "Отправление: другое"
        func run(_ managed: Set<String>) -> [AppNotice] {
            NotificationRules.diff(
                old: [old.ref: old], new: [s.ref: s], oldNodes: nodes, newNodes: nodes,
                settings: NotifySettings(storm: false, event: true, delay: true, queue: false),
                labels: Labels(lang: .ru, nodes: nodes), pushManagedRefs: managed)
        }
        XCTAssertEqual(Set(run([]).map(\.kind)), [.event, .delay])
        XCTAssertEqual(run([s.ref]).map(\.kind), [.delay])
    }

    func test_late401_keepsNewerToken() async throws {
        let store = InMemoryTokenStore(token: "A")
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let api = HTTPAccountAPI(
            baseURL: URL(string: "http://localhost:8000")!, tokens: store, session: URLSession(configuration: config))
        StubProtocol.handler = { _ in
            store.save("B")  // за время запроса вход выдал новый токен
            return (401, Data())
        }
        do {
            _ = try await api.me()
            XCTFail("ждали ошибку")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }
        XCTAssertEqual(store.load(), "B")
    }

    func test_loginResult_redactsToken() throws {
        let me = try String(decoding: accountData("me"), as: UTF8.self)
        let json = #"{"token":"SECRET-TOKEN-XYZ","me":\#(me)}"#
        let result = try APIDate.makeDecoder().decode(LoginResult.self, from: Data(json.utf8))
        XCTAssertFalse(String(describing: result).contains("SECRET-TOKEN-XYZ"))
        XCTAssertFalse(String(reflecting: result).contains("SECRET-TOKEN-XYZ"))
        XCTAssertFalse("\(result)".contains("SECRET-TOKEN-XYZ"))
    }
}
