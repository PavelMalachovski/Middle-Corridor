import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Клиент API аккаунтов (`/api/v1/auth`, `/me`, `/my/shipments`, `/orgs`) — по методу на эндпоинт.
/// Ошибки — `APIError`: нет входа → `.unauthorized`, нет доступа или объекта → `.notFound`
/// (сервер не отличает), отказ по существу → `.rejected(код)`.
public protocol AccountAPI: Sendable {
    /// Письмо с кодом; ответ одинаков для любого адреса.
    func requestCode(email: String) async throws
    /// Обмен кода на сессию; токен кладётся в `TokenStore`.
    func verify(email: String, code: String, deviceName: String) async throws -> LoginResult
    /// Выход: токен стирается локально в любом случае. `apnsToken` — токен этого устройства:
    /// сервер отзывает его, чтобы push предыдущего пользователя сюда больше не шли.
    func logout(apnsToken: String?) async throws
    func me() async throws -> Me
    func registerDevice(apnsToken: String, environment: String) async throws
    func myShipments() async throws -> [MyShipment]
    func create(_ shipment: NewShipment) async throws -> MyShipment
    func update(ref: String, _ patch: ShipmentPatch) async throws -> MyShipment
    func addEvent(ref: String, _ event: CheckpointEventInput) async throws -> CheckpointEventRecord
    func events(ref: String) async throws -> [CheckpointEventRecord]
    func share(ref: String, orgId: Int) async throws
    func archive(ref: String) async throws
    func members(orgId: Int) async throws -> [OrgMember]
    func invite(orgId: Int, email: String, role: AccountRole, nodeCodes: [String]) async throws -> Invitation
    func revoke(orgId: Int, userId: Int) async throws
    func clients(orgId: Int) async throws -> [OrgSummary]
}

public struct HTTPAccountAPI: AccountAPI {
    public let baseURL: URL
    private let tokens: any TokenStore
    private let session: URLSession
    private let timeout: TimeInterval

    public init(
        baseURL: URL, tokens: any TokenStore, session: URLSession = .shared, timeout: TimeInterval = 15
    ) {
        self.baseURL = baseURL
        self.tokens = tokens
        self.session = session
        self.timeout = timeout
    }

    public func requestCode(email: String) async throws {
        try await sendVoid("POST", "auth/code", body: ["email": email], authorized: false)
    }

    public func verify(email: String, code: String, deviceName: String) async throws -> LoginResult {
        let body = ["email": email, "code": code, "device_name": deviceName]
        // 401 здесь — неверный код, а не конец сессии: токен не трогаем
        let result: LoginResult = try await send("POST", "auth/verify", body: body, authorized: false)
        tokens.save(result.token)
        return result
    }

    public func logout(apnsToken: String?) async throws {
        defer { tokens.save(nil) }
        do {
            try await sendVoid(
                "POST", "auth/logout", body: apnsToken.map { ["apns_token": $0] })
        } catch APIError.unauthorized {
            // сессия уже недействительна — выходить больше не из чего
        }
    }

    public func me() async throws -> Me { try await send("GET", "me") }

    public func registerDevice(apnsToken: String, environment: String) async throws {
        try await sendVoid(
            "POST", "me/devices", body: ["apns_token": apnsToken, "environment": environment])
    }

    public func myShipments() async throws -> [MyShipment] { try await send("GET", "my/shipments") }

    public func create(_ shipment: NewShipment) async throws -> MyShipment {
        try await send("POST", "my/shipments", body: shipment)
    }

    public func update(ref: String, _ patch: ShipmentPatch) async throws -> MyShipment {
        try await send("PATCH", "my/shipments/\(ref)", body: patch)
    }

    public func addEvent(ref: String, _ event: CheckpointEventInput) async throws -> CheckpointEventRecord {
        try await send("POST", "my/shipments/\(ref)/events", body: event)
    }

    public func events(ref: String) async throws -> [CheckpointEventRecord] {
        try await send("GET", "my/shipments/\(ref)/events")
    }

    public func share(ref: String, orgId: Int) async throws {
        try await sendVoid("POST", "my/shipments/\(ref)/share", body: ["org_id": orgId])
    }

    public func archive(ref: String) async throws {
        try await sendVoid("POST", "my/shipments/\(ref)/archive")
    }

    public func members(orgId: Int) async throws -> [OrgMember] {
        try await send("GET", "orgs/\(orgId)/members")
    }

    public func invite(
        orgId: Int, email: String, role: AccountRole, nodeCodes: [String]
    ) async throws -> Invitation {
        let body = InviteBody(email: email, role: role.rawValue, nodeCodes: nodeCodes)
        return try await send("POST", "orgs/\(orgId)/invitations", body: body)
    }

    public func revoke(orgId: Int, userId: Int) async throws {
        try await sendVoid("DELETE", "orgs/\(orgId)/members/\(userId)")
    }

    public func clients(orgId: Int) async throws -> [OrgSummary] {
        try await send("GET", "orgs/\(orgId)/clients")
    }

    // MARK: - Транспорт

    private struct InviteBody: Encodable {
        let email: String
        let role: String
        let nodeCodes: [String]
    }

    private func send<T: Decodable>(
        _ method: String, _ path: String, body: (any Encodable)? = nil, authorized: Bool = true
    ) async throws -> T {
        let data = try await perform(method, path, body: body, authorized: authorized)
        do {
            return try APIDate.makeDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.from(error)
        }
    }

    private func sendVoid(
        _ method: String, _ path: String, body: (any Encodable)? = nil, authorized: Bool = true
    ) async throws {
        _ = try await perform(method, path, body: body, authorized: authorized)
    }

    private func perform(
        _ method: String, _ path: String, body: (any Encodable)?, authorized: Bool
    ) async throws -> Data {
        var url = baseURL.appending(path: "api/v1")
        for part in path.split(separator: "/") { url.append(component: String(part)) }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        var sentToken: String?
        if authorized {
            // без токена запрос не уходит: сервер всё равно ответил бы 401
            guard let token = tokens.load() else { throw APIError.unauthorized }
            sentToken = token
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try Self.encode(body)
        }
        let result: (Data, URLResponse)
        do {
            result = try await session.data(for: request)
        } catch {
            throw APIError.from(error)
        }
        let (data, response) = result
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        switch status {
        case 200..<300: return data
        case 401:
            // поздний 401 на старый токен не должен стереть новый, выданный за это время
            if let sentToken, tokens.load() == sentToken { tokens.save(nil) }
            throw APIError.unauthorized
        case 404: throw APIError.notFound
        case 422: throw APIError.rejected(Self.rejectionCode(data))
        default: throw APIError.http(status)
        }
    }

    private static func encode(_ body: any Encodable) throws -> Data {
        try APIDate.makeEncoder().encode(AnyEncodable(body))
    }

    /// `{"detail": "node_not_allowed"}` → код; ошибка схемы FastAPI (detail — список) → `invalid`.
    static func rejectionCode(_ data: Data) -> String {
        struct Detail: Decodable { let detail: String }
        return (try? JSONDecoder().decode(Detail.self, from: data))?.detail ?? "invalid"
    }
}

private struct AnyEncodable: Encodable {
    let base: any Encodable
    init(_ base: any Encodable) { self.base = base }
    func encode(to encoder: Encoder) throws { try base.encode(to: encoder) }
}
