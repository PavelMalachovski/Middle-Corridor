#if DEBUG
    import Foundation
    import MCCore

    /// Сервер аккаунтов для UI-тестов и показа (`-mc-fake-api`): код `000000`; экспедитор
    /// «Caspian Freight» (владелец) и агент «Aktau Port Agency» в Актау; два груза из фикстуры
    /// `my_shipments.json` (второй — её копия под другим номером и компанией, без стоянки).
    /// Создание груза, правка, события и приглашения меняют состояние в памяти (`FakeAccountState`)
    /// — живёт, пока жив процесс.
    struct FakeAccountAPI: AccountAPI {
        static let code = "000000"
        /// Токен фейка несёт адрес входа — `me()` отвечает тем же e-mail.
        private static let prefix = "fake-session:"
        let tokens: any TokenStore
        var state = FakeAccountState()

        func requestCode(email: String) async throws {
            try await Task.sleep(for: .milliseconds(200))
        }

        func verify(email: String, code: String, deviceName: String) async throws -> LoginResult {
            try await Task.sleep(for: .milliseconds(200))
            guard code == Self.code else { throw APIError.unauthorized }
            let me = try JSONSerialization.jsonObject(with: Self.meJSON(email: email))
            let body = try JSONSerialization.data(withJSONObject: ["token": Self.prefix + email, "me": me])
            let result = try APIDate.makeDecoder().decode(LoginResult.self, from: body)
            tokens.save(result.token)
            return result
        }

        func logout() async throws {
            tokens.save(nil)
        }

        func me() async throws -> Me {
            let email = try authorize()
            return try APIDate.makeDecoder().decode(Me.self, from: Self.meJSON(email: email))
        }

        func registerDevice(apnsToken: String, environment: String) async throws {
            try authorize()
        }

        func myShipments() async throws -> [MyShipment] {
            try authorize()
            try await Task.sleep(for: .milliseconds(200))
            return try await state.shipments()
        }

        func create(_ shipment: NewShipment) async throws -> MyShipment {
            try authorize()
            try await Task.sleep(for: .milliseconds(200))
            guard shipment.orgId == 1 else { throw APIError.notFound }  // экспедитор-владелец — только тут
            return try await state.create(shipment)
        }

        func update(ref: String, _ patch: ShipmentPatch) async throws -> MyShipment {
            try authorize()
            return try await state.update(ref: ref, patch)
        }

        func addEvent(ref: String, _ event: CheckpointEventInput) async throws -> CheckpointEventRecord {
            try authorize()
            try await Task.sleep(for: .milliseconds(200))
            return try await state.addEvent(ref: ref, event)
        }

        func events(ref: String) async throws -> [CheckpointEventRecord] {
            try authorize()
            return try await state.events(ref: ref)
        }

        func share(ref: String, orgId: Int) async throws {
            try authorize()
            guard orgId == FakeAccountState.clientId else { throw APIError.notFound }
        }

        func archive(ref: String) async throws { throw APIError.notFound }

        func members(orgId: Int) async throws -> [OrgMember] {
            let email = try authorize()
            guard orgId == 1 else { throw APIError.notFound }  // агент Актау команду не видит
            return try await state.members(selfEmail: email)
        }

        func invite(orgId: Int, email: String, role: AccountRole, nodeCodes: [String]) async throws -> Invitation {
            try authorize()
            try await Task.sleep(for: .milliseconds(200))
            guard orgId == 1 else { throw APIError.notFound }
            if !nodeCodes.isEmpty, role != .agent { throw APIError.rejected("nodes_for_agent_only") }
            return try await state.invite(email: email)
        }

        func revoke(orgId: Int, userId: Int) async throws {
            try authorize()
            guard orgId == 1 else { throw APIError.notFound }
            try await state.revoke(userId: userId)
        }

        func clients(orgId: Int) async throws -> [OrgSummary] {
            try authorize()
            guard orgId == 1 else { return [] }
            let json: [[String: Any]] = [["id": FakeAccountState.clientId, "name": "Kostanay Motors", "kind": "client"]]
            return try APIDate.makeDecoder().decode([OrgSummary].self, from: JSONSerialization.data(withJSONObject: json))
        }

        /// E-mail сессии; нет токена — 401, как у сервера.
        @discardableResult
        private func authorize() throws -> String {
            guard let token = tokens.load(), token.hasPrefix(Self.prefix) else { throw APIError.unauthorized }
            return String(token.dropFirst(Self.prefix.count))
        }

        private static func meJSON(email: String) throws -> Data {
            let me: [String: Any] = [
                "id": 1, "email": email, "name": NSNull(), "locale": "ru", "is_platform_admin": false,
                "memberships": [
                    [
                        "org_id": 1, "org_name": "Caspian Freight", "org_kind": "forwarder", "role": "owner",
                        "node_codes": [String](),
                    ],
                    [
                        "org_id": 2, "org_name": "Aktau Port Agency", "org_kind": "forwarder", "role": "agent",
                        "node_codes": ["AKTAU"],
                    ],
                ],
            ]
            return try JSONSerialization.data(withJSONObject: me)
        }
    }
#endif
