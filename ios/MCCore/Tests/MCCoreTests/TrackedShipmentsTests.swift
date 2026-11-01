import Foundation
import XCTest
@testable import MCCore

/// Фейковый API на фикстурах; `offline` — имитация пропавшей сети.
actor FakeAPI: CorridorAPI {
    private var offline = false
    private(set) var shipmentCalls = 0
    private let known: [String: Shipment]
    private let snap: MapSnapshot

    init() throws {
        snap = try Fixture.snapshot()
        var known: [String: Shipment] = [:]
        for ref in ["MC-26-0412", "MC-26-0398"] { known[ref] = try Fixture.shipment(ref) }
        self.known = known
    }

    private var delay: Duration = .zero

    func setOffline(_ value: Bool) { offline = value }
    func setDelay(_ value: Duration) { delay = value }

    func snapshot() async throws -> MapSnapshot {
        if delay > .zero { try await Task.sleep(for: delay) }
        try Task.checkCancellation()
        if offline { throw APIError.offline }
        return snap
    }

    func shipment(ref: String) async throws -> Shipment {
        shipmentCalls += 1
        if delay > .zero { try await Task.sleep(for: delay) }
        try Task.checkCancellation()
        if offline { throw APIError.offline }
        guard let s = known[ref] else { throw APIError.notFound }
        return s
    }
}

@MainActor
final class TrackedShipmentsTests: XCTestCase {
    private func make(_ storage: MemoryRefStorage = MemoryRefStorage()) throws -> (TrackedShipments, FakeAPI, MemoryRefStorage) {
        let api = try FakeAPI()
        return (TrackedShipments(api: api, storage: storage, now: { Date(timeIntervalSince1970: 1000) }), api, storage)
    }

    private func addError(_ store: TrackedShipments, _ input: String) async -> AddError? {
        do {
            try await store.add(input)
            return nil
        } catch {
            return error
        }
    }

    func test_addNormalizesAndPersists() async throws {
        let (store, _, storage) = try make()
        let ref = try await store.add(" mc-26-0412 ")
        XCTAssertEqual(ref, "MC-26-0412")
        XCTAssertEqual(store.refs, ["MC-26-0412"])
        XCTAssertEqual(storage.load(), ["MC-26-0412"])
        XCTAssertEqual(store.rows.first?.shipment?.ref, "MC-26-0412")
    }

    func test_addTwiceDifferentCase_keepsOne() async throws {
        let (store, api, _) = try make()
        try await store.add("MC-26-0412")
        try await store.add("mcstatus://s/mc-26-0412")
        XCTAssertEqual(store.refs, ["MC-26-0412"])
        let calls = await api.shipmentCalls
        XCTAssertEqual(calls, 1)
    }

    func test_newestFirst() async throws {
        let (store, _, _) = try make()
        try await store.add("MC-26-0412")
        try await store.add("MC-26-0398")
        XCTAssertEqual(store.refs, ["MC-26-0398", "MC-26-0412"])
    }

    func test_addUnknown_throwsNotFound_andStoresNothing() async throws {
        let (store, _, storage) = try make()
        let error = await addError(store, "MC-00-0000")
        XCTAssertEqual(error, .notFound)
        XCTAssertEqual(store.refs, [])
        XCTAssertEqual(storage.load(), [])
    }

    func test_addInvalid_throwsInvalidRef_noRequest() async throws {
        let (store, api, _) = try make()
        let error = await addError(store, "привет")
        XCTAssertEqual(error, .invalidRef)
        let calls = await api.shipmentCalls
        XCTAssertEqual(calls, 0)
    }

    func test_addOffline_throwsOffline() async throws {
        let (store, api, _) = try make()
        await api.setOffline(true)
        let error = await addError(store, "MC-26-0412")
        XCTAssertEqual(error, .offline)
        XCTAssertEqual(store.refs, [])
    }

    func test_remove() async throws {
        let (store, _, storage) = try make()
        try await store.add("MC-26-0412")
        store.remove("MC-26-0412")
        XCTAssertEqual(store.refs, [])
        XCTAssertNil(store.shipments["MC-26-0412"])
        XCTAssertEqual(storage.load(), [])
    }

    func test_refreshOffline_keepsOldData() async throws {
        let (store, api, _) = try make(MemoryRefStorage(["MC-26-0412"]))
        await store.refresh()
        XCTAssertNil(store.lastError)
        XCTAssertEqual(store.updatedAt, Date(timeIntervalSince1970: 1000))
        XCTAssertNotNil(store.snapshot)
        XCTAssertEqual(store.rows.first?.shipment?.ref, "MC-26-0412")

        await api.setOffline(true)
        await store.refresh()
        XCTAssertEqual(store.lastError, .offline)
        XCTAssertEqual(store.rows.first?.shipment?.ref, "MC-26-0412")
        XCTAssertNotNil(store.snapshot)
        XCTAssertEqual(store.updatedAt, Date(timeIntervalSince1970: 1000))
        XCTAssertFalse(store.isRefreshing)
    }

    func test_loadsRefsFromStorageOnInit() throws {
        let (store, _, _) = try make(MemoryRefStorage(["MC-26-0398", "MC-26-0412"]))
        XCTAssertEqual(store.refs, ["MC-26-0398", "MC-26-0412"])
        XCTAssertNil(store.rows.first?.shipment)  // данные ещё не загружены
    }

    func test_cancelledRefresh_isNotOffline() async throws {
        // SwiftUI отменяет .task/.refreshable (переход в карточку) — это не «нет связи»
        let (store, api, _) = try make(MemoryRefStorage(["MC-26-0412"]))
        await api.setDelay(.seconds(5))
        let task = Task { await store.refresh() }
        try await Task.sleep(for: .milliseconds(50))
        task.cancel()
        await task.value
        XCTAssertNil(store.lastError)
        XCTAssertNil(store.updatedAt)
        XCTAssertFalse(store.isRefreshing)
    }

    func test_refreshUnknownRef_isMissing_notLoadingForever() async throws {
        let (store, _, _) = try make(MemoryRefStorage(["MC-00-0000", "MC-26-0412"]))
        await store.refresh()
        XCTAssertEqual(store.missing, ["MC-00-0000"])
        XCTAssertNil(store.lastError)
        XCTAssertEqual(store.rows.map(\.ref), ["MC-00-0000", "MC-26-0412"])
    }

    func test_removeClearsMissing() async throws {
        let (store, _, _) = try make(MemoryRefStorage(["MC-00-0000"]))
        await store.refresh()
        store.remove("MC-00-0000")
        XCTAssertEqual(store.missing, [])
    }

    // MARK: офлайн-кэш

    func test_startOffline_showsCachedData() async throws {
        let api = try FakeAPI()
        await api.setOffline(true)
        let cached = try Fixture.shipment("MC-26-0412")
        let cache = MemoryShipmentCache(
            CachedState(shipments: [cached.ref: cached], snapshot: nil, updatedAt: Date(timeIntervalSince1970: 500)))
        let store = TrackedShipments(
            api: api, storage: MemoryRefStorage(["MC-26-0412"]), cache: cache,
            now: { Date(timeIntervalSince1970: 1000) })
        XCTAssertEqual(store.shipments["MC-26-0412"], cached)
        XCTAssertEqual(store.updatedAt, Date(timeIntervalSince1970: 500))

        await store.refresh()
        XCTAssertEqual(store.shipments["MC-26-0412"], cached)
        XCTAssertEqual(store.lastError, .offline)
        XCTAssertEqual(store.updatedAt, Date(timeIntervalSince1970: 500))
    }

    func test_cacheIgnoresRefsNoLongerTracked() throws {
        let cached = try Fixture.shipment("MC-26-0412")
        let cache = MemoryShipmentCache(CachedState(shipments: [cached.ref: cached], snapshot: nil, updatedAt: nil))
        let store = TrackedShipments(api: try FakeAPI(), storage: MemoryRefStorage(), cache: cache)
        XCTAssertTrue(store.shipments.isEmpty)
    }

    func test_refreshWritesCache() async throws {
        let cache = MemoryShipmentCache()
        let store = TrackedShipments(
            api: try FakeAPI(), storage: MemoryRefStorage(["MC-26-0398"]), cache: cache,
            now: { Date(timeIntervalSince1970: 1000) })
        await store.refresh()
        let saved = try XCTUnwrap(cache.load())
        XCTAssertEqual(Set(saved.shipments.keys), ["MC-26-0398"])
        XCTAssertNotNil(saved.snapshot)
        XCTAssertEqual(saved.updatedAt, Date(timeIntervalSince1970: 1000))
    }

    func test_addWritesCache() async throws {
        let cache = MemoryShipmentCache()
        let store = TrackedShipments(api: try FakeAPI(), storage: MemoryRefStorage(), cache: cache)
        try await store.add("MC-26-0412")
        XCTAssertNotNil(cache.load()?.shipments["MC-26-0412"])
    }

    func test_removeDropsFromCache() async throws {
        let cache = MemoryShipmentCache()
        let store = TrackedShipments(api: try FakeAPI(), storage: MemoryRefStorage(), cache: cache)
        try await store.add("MC-26-0412")
        store.remove("MC-26-0412")
        XCTAssertNil(cache.load()?.shipments["MC-26-0412"])
    }

    // MARK: изменения после обновления

    func test_refreshReportsChange() async throws {
        let api = try FakeAPI()
        let store = TrackedShipments(api: api, storage: MemoryRefStorage(["MC-26-0398"]))
        var changes: [StoreChange] = []
        store.onChange = { changes.append($0) }
        await store.refresh()
        await store.refresh()
        XCTAssertEqual(changes.count, 2)
        XCTAssertTrue(changes[0].oldShipments.isEmpty)
        XCTAssertEqual(changes[1].oldShipments["MC-26-0398"], changes[1].newShipments["MC-26-0398"])
        XCTAssertFalse(changes[1].newNodes.isEmpty)
        XCTAssertEqual(changes[1].oldNodes.count, changes[1].newNodes.count)
    }

    func test_cancelledRefresh_reportsNothing() async throws {
        let api = try FakeAPI()
        await api.setDelay(.milliseconds(300))
        let store = TrackedShipments(api: api, storage: MemoryRefStorage(["MC-26-0398"]))
        var count = 0
        store.onChange = { _ in count += 1 }
        let task = Task { await store.refresh() }
        try await Task.sleep(for: .milliseconds(50))
        task.cancel()
        await task.value
        XCTAssertEqual(count, 0)
    }

    func test_add_reportsNothing() async throws {
        let store = TrackedShipments(api: try FakeAPI(), storage: MemoryRefStorage())
        var count = 0
        store.onChange = { _ in count += 1 }
        try await store.add("MC-26-0412")
        XCTAssertEqual(count, 0)
    }
}
