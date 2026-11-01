import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Источник данных коридора — `/api/v1` бэкенда (или фейк в UI-тестах).
public protocol CorridorAPI: Sendable {
    func snapshot() async throws -> MapSnapshot
    func shipment(ref: String) async throws -> Shipment
    /// Часы демо; сервер без пульта (не мок или без DEMO_CONTROL) — `APIError.notFound`.
    func demoClock() async throws -> DemoClockState
    func demo(_ action: DemoAction) async throws -> DemoClockState
}

extension CorridorAPI {
    // по умолчанию пульта нет — как у боевого сервера
    public func demoClock() async throws -> DemoClockState { throw APIError.notFound }
    public func demo(_ action: DemoAction) async throws -> DemoClockState { throw APIError.notFound }
}

/// Действие пульта ведущего: перевести часы, следующий шаг истории, сброс.
public enum DemoAction: Sendable, Equatable {
    case advance(hours: Double)
    case nextBeat
    case reset

    var body: [String: any Sendable] {
        switch self {
        case .advance(let hours): ["action": "advance", "hours": hours]
        case .nextBeat: ["action": "next_beat"]
        case .reset: ["action": "reset"]
        }
    }
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

    public func demoClock() async throws -> DemoClockState {
        try await get(baseURL.appending(path: "api/v1/demo/clock"))
    }

    public func demo(_ action: DemoAction) async throws -> DemoClockState {
        var request = URLRequest(url: baseURL.appending(path: "api/v1/demo/clock"), timeoutInterval: timeout)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: action.body)
        return try await send(request)
    }

    private func get<T: Decodable>(_ url: URL) async throws -> T {
        try await send(URLRequest(url: url, timeoutInterval: timeout))
    }

    private func send<T: Decodable>(_ base: URLRequest) async throws -> T {
        var request = base
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
