import Foundation
import Observation

/// Где хранится список отслеживаемых номеров. Последние данные по ним — в `ShipmentCache`.
public protocol RefStorage: Sendable {
    func load() -> [String]
    func save(_ refs: [String])
}

public struct UserDefaultsRefStorage: RefStorage {
    public static let key = "mc.tracked"
    private let suiteName: String?

    public init(suiteName: String? = nil) { self.suiteName = suiteName }

    public func load() -> [String] { defaults.stringArray(forKey: Self.key) ?? [] }
    public func save(_ refs: [String]) { defaults.set(refs, forKey: Self.key) }

    private var defaults: UserDefaults { suiteName.flatMap(UserDefaults.init(suiteName:)) ?? .standard }
}

/// Хранилище в памяти — для тестов и демо-режима на фейковом API.
public final class MemoryRefStorage: RefStorage, @unchecked Sendable {
    private let lock = NSLock()
    private var refs: [String]

    public init(_ refs: [String] = []) { self.refs = refs }

    public func load() -> [String] { lock.withLock { refs } }
    public func save(_ refs: [String]) { lock.withLock { self.refs = refs } }
}

public enum AddError: Error, Equatable, Sendable {
    /// В строке нет номера груза.
    case invalidRef
    /// Сервер такого груза не знает.
    case notFound
    /// Нет связи с сервером.
    case offline
    /// Сервер ответил ошибкой или непонятным ответом.
    case server
}

/// Строка списка «Мои грузы»: номер есть всегда, данных может не быть (ещё не загрузились).
public struct TrackedRow: Identifiable, Sendable, Hashable {
    public var id: String { ref }
    public let ref: String
    public let shipment: Shipment?
}

/// Что было до обновления и что стало — для уведомлений и Live Activity.
public struct StoreChange: Sendable {
    public let oldShipments: [String: Shipment]
    public let newShipments: [String: Shipment]
    public let oldNodes: [NodeStatus]
    public let newNodes: [NodeStatus]
}

/// «Мои грузы»: номера, последние данные по ним и снимок коридора.
@MainActor
@Observable
public final class TrackedShipments {
    public private(set) var refs: [String]
    public private(set) var shipments: [String: Shipment] = [:]
    public private(set) var snapshot: MapSnapshot?
    /// Ошибка последнего обновления; старые данные при этом остаются на экране.
    public private(set) var lastError: APIError?
    /// Когда данные в последний раз пришли целиком.
    public private(set) var updatedAt: Date?
    public private(set) var isRefreshing = false
    /// Номера, которых сервер не знает (404 при последнем обновлении): «не найден», а не вечное «загружается».
    public private(set) var missing: Set<String> = []

    /// Вызывается после каждого завершённого обновления (не при отмене и не при `add`).
    @ObservationIgnored public var onChange: (@MainActor (StoreChange) -> Void)?

    private let api: any CorridorAPI
    private let storage: any RefStorage
    private let cache: any ShipmentCache
    private let now: @Sendable () -> Date

    public init(
        api: any CorridorAPI,
        storage: any RefStorage,
        cache: any ShipmentCache = MemoryShipmentCache(),
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.api = api
        self.storage = storage
        self.cache = cache
        self.now = now
        let refs = storage.load()
        self.refs = refs
        if let cached = cache.load() {
            shipments = cached.shipments.filter { refs.contains($0.key) }
            snapshot = cached.snapshot
            updatedAt = cached.updatedAt
        }
    }

    private func persist() {
        cache.save(CachedState(shipments: shipments, snapshot: snapshot, updatedAt: updatedAt))
    }

    public var rows: [TrackedRow] {
        refs.map { TrackedRow(ref: $0, shipment: shipments[$0]) }
    }

    /// Добавляет груз по номеру или ссылке; возвращает нормализованный номер.
    /// Уже отслеживаемый номер не запрашивается повторно.
    @discardableResult
    public func add(_ input: String) async throws(AddError) -> String {
        guard let ref = ShipmentRef.parse(input) else { throw .invalidRef }
        if refs.contains(ref) { return ref }
        let shipment: Shipment
        do {
            shipment = try await api.shipment(ref: ref)
        } catch {
            switch APIError.from(error) {
            case .notFound: throw .notFound
            case .offline: throw .offline
            case .http, .decoding: throw .server
            }
        }
        guard !refs.contains(ref) else { return ref }  // пока ждали ответа, добавили ещё раз
        shipments[ref] = shipment
        missing.remove(ref)
        refs.insert(ref, at: 0)
        storage.save(refs)
        persist()
        return ref
    }

    public func remove(_ ref: String) {
        refs.removeAll { $0 == ref }
        shipments[ref] = nil
        missing.remove(ref)
        storage.save(refs)
        persist()
    }

    /// Снимок коридора и все грузы — параллельно. Ошибка не стирает старые данные — уходит
    /// в lastError. Отменённое обновление (SwiftUI снимает .task при переходе) ничего не пишет:
    /// отмена — не «нет связи».
    public func refresh() async {
        isRefreshing = true
        defer { isRefreshing = false }
        let api = self.api
        let refs = self.refs

        async let snapshotResult = Self.load { try await api.snapshot() }
        let results = await withTaskGroup(of: (String, Result<Shipment, APIError>).self) { group in
            for ref in refs {
                group.addTask { (ref, await Self.load { try await api.shipment(ref: ref) }) }
            }
            var out: [(String, Result<Shipment, APIError>)] = []
            for await result in group { out.append(result) }
            return out
        }
        let snapshotLoaded = await snapshotResult

        guard !Task.isCancelled else { return }

        let oldShipments = shipments
        let oldNodes = snapshot?.nodes ?? []
        var failure: APIError?
        switch snapshotLoaded {
        case .success(let snap): snapshot = snap
        case .failure(let error): failure = error
        }

        for (ref, result) in results where self.refs.contains(ref) {  // пока грузили, могли удалить
            switch result {
            case .success(let shipment):
                shipments[ref] = shipment
                missing.remove(ref)
            case .failure(.notFound):
                missing.insert(ref)  // последнее, что знали, остаётся на экране
            case .failure(let error):
                failure = failure ?? error
            }
        }

        lastError = failure
        if failure == nil { updatedAt = now() }
        persist()
        onChange?(
            StoreChange(
                oldShipments: oldShipments, newShipments: shipments,
                oldNodes: oldNodes, newNodes: snapshot?.nodes ?? []))
    }

    private nonisolated static func load<T: Sendable>(
        _ body: @Sendable () async throws -> T
    ) async -> Result<T, APIError> {
        do {
            return .success(try await body())
        } catch {
            return .failure(APIError.from(error))
        }
    }
}
