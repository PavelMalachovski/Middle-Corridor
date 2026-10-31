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

    func setOffline(_ value: Bool) { offline = value }

    func snapshot() async throws -> MapSnapshot {
        if offline { throw APIError.offline }
        return snap
    }

    func shipment(ref: String) async throws -> Shipment {
        shipmentCalls += 1
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
}
