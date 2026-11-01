import Foundation

/// Последнее, что приложение знало: грузы, снимок коридора и время данных.
/// Виден сразу при запуске и без сети («данные от …»).
public struct CachedState: Codable, Sendable {
    public var shipments: [String: Shipment]
    public var snapshot: MapSnapshot?
    public var updatedAt: Date?
    /// С какого сервера данные: после смены адреса чужой кэш не показываем как свой.
    public var server: String?

    public init(shipments: [String: Shipment], snapshot: MapSnapshot?, updatedAt: Date?, server: String? = nil) {
        self.shipments = shipments
        self.snapshot = snapshot
        self.updatedAt = updatedAt
        self.server = server
    }
}

/// Где лежит офлайн-кэш. Ошибка чтения — это «кэша нет», а не падение.
public protocol ShipmentCache: Sendable {
    func load() -> CachedState?
    func save(_ state: CachedState)
}

/// Один JSON-файл в каталоге (Application Support или контейнер App Group для виджета).
public struct FileShipmentCache: ShipmentCache {
    public static let fileName = "state.json"
    public let directory: URL

    public init(directory: URL) { self.directory = directory }

    private var url: URL { directory.appending(path: Self.fileName) }

    public func load() -> CachedState? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? APIDate.makeDecoder().decode(CachedState.self, from: data)
    }

    public func save(_ state: CachedState) {
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try APIDate.makeEncoder().encode(state).write(to: url, options: .atomic)
        } catch {
            // кэш — удобство: не записали, значит при следующем запуске без сети данных не будет
        }
    }
}

/// Кэш в памяти — для тестов и демо на фейковом API.
public final class MemoryShipmentCache: ShipmentCache, @unchecked Sendable {
    private let lock = NSLock()
    private var state: CachedState?

    public init(_ state: CachedState? = nil) { self.state = state }

    public func load() -> CachedState? { lock.withLock { state } }
    public func save(_ state: CachedState) { lock.withLock { self.state = state } }
}
