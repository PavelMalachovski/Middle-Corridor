import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Источник данных коридора — `/api/v1` бэкенда (или фейк в UI-тестах).
public protocol CorridorAPI: Sendable {
    func snapshot() async throws -> MapSnapshot
    func shipment(ref: String) async throws -> Shipment
}

public enum APIError: Error, Equatable, Sendable {
    case notFound
    case http(Int)
    /// Нет связи с сервером: сеть, таймаут, Мак спит, другая Wi‑Fi.
    case offline
    case decoding(String)

    /// Любая ошибка клиента → APIError (URLError — это «нет связи»).
    public static func from(_ error: any Error) -> APIError {
        switch error {
        case let error as APIError: error
        case is URLError: .offline
        case let error as DecodingError: .decoding(String(describing: error))
        default: .offline
        }
    }
}

public struct HTTPCorridorAPI: CorridorAPI {
    public let baseURL: URL
    private let session: URLSession
    private let timeout: TimeInterval

    public init(baseURL: URL, session: URLSession = .shared, timeout: TimeInterval = 10) {
        self.baseURL = baseURL
        self.session = session
        self.timeout = timeout
    }

    public func snapshot() async throws -> MapSnapshot {
        try await get(baseURL.appending(path: "api/v1/snapshot"))
    }

    public func shipment(ref: String) async throws -> Shipment {
        try await get(baseURL.appending(path: "api/v1/shipments").appending(component: ref))
    }

    private func get<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let result: (Data, URLResponse)
        do {
            result = try await session.data(for: request)
        } catch {
            throw APIError.from(error)
        }
        let (data, response) = result
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 404 { throw APIError.notFound }
        guard (200..<300).contains(status) else { throw APIError.http(status) }
        do {
            return try APIDate.makeDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.from(error)
        }
    }
}
