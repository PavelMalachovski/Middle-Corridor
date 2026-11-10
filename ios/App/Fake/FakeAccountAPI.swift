#if DEBUG
    import Foundation
    import MCCore

    /// Сервер аккаунтов для UI-тестов и показа (`-mc-fake-api`): код `000000`; экспедитор
    /// «Caspian Freight» (владелец) и агент «Aktau Port Agency» в Актау; два груза из фикстуры
    /// `my_shipments.json` (второй — её копия под другим номером и компанией).
    struct FakeAccountAPI: AccountAPI {
        static let code = "000000"
        /// Токен фейка несёт адрес входа — `me()` отвечает тем же e-mail без своего состояния.
        private static let prefix = "fake-session:"
        let tokens: any TokenStore

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
            guard let url = Bundle.main.url(forResource: "my_shipments", withExtension: "json"),
                let list = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]],
                var first = list.first, var shipment = first["shipment"] as? [String: Any]
            else { throw APIError.http(500) }
            shipment["client"] = "Caspian Freight"
            first["shipment"] = shipment
            var second = first
            shipment["ref"] = "MC-27-0002"
            shipment["client"] = "Aktau Port Agency"
            second["shipment"] = shipment
            second["org_id"] = 2
            second["can_manage"] = false
            second["event_nodes"] = ["AKTAU"]
            let data = try JSONSerialization.data(withJSONObject: [first, second])
            return try APIDate.makeDecoder().decode([MyShipment].self, from: data)
        }

        // Создание, события и компании — следующий этап; фейку пока хватает отказа.
        func create(_ shipment: NewShipment) async throws -> MyShipment { throw APIError.notFound }
        func update(ref: String, _ patch: ShipmentPatch) async throws -> MyShipment { throw APIError.notFound }
        func addEvent(ref: String, _ event: CheckpointEventInput) async throws -> CheckpointEventRecord {
            throw APIError.notFound
        }
        func events(ref: String) async throws -> [CheckpointEventRecord] { [] }
        func share(ref: String, orgId: Int) async throws { throw APIError.notFound }
        func archive(ref: String) async throws { throw APIError.notFound }
        func members(orgId: Int) async throws -> [OrgMember] { [] }
        func invite(orgId: Int, email: String, role: AccountRole, nodeCodes: [String]) async throws -> Invitation {
            throw APIError.notFound
        }
        func revoke(orgId: Int, userId: Int) async throws { throw APIError.notFound }
        func clients(orgId: Int) async throws -> [OrgSummary] { [] }

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
