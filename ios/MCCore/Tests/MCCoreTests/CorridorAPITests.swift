import Foundation
import XCTest
@testable import MCCore

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Подменяет сеть: каждый запрос отдаётся обработчику `handler`.
final class StubProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (Int, Data))?
    nonisolated(unsafe) static var lastPath: String?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lastPath = request.url?.path
        do {
            guard let handler = Self.handler, let url = request.url else { throw URLError(.badURL) }
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class CorridorAPITests: XCTestCase {
    private func api() -> HTTPCorridorAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        return HTTPCorridorAPI(baseURL: URL(string: "http://localhost:8000")!, session: URLSession(configuration: config))
    }

    override func tearDown() {
        StubProtocol.handler = nil
        StubProtocol.lastPath = nil
    }

    func test_shipment_ok() async throws {
        let body = try Fixture.data("shipment_MC-26-0412")
        StubProtocol.handler = { _ in (200, body) }
        let s = try await api().shipment(ref: "MC-26-0412")
        XCTAssertEqual(s.ref, "MC-26-0412")
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/shipments/MC-26-0412")
    }

    func test_snapshot_ok() async throws {
        let body = try Fixture.data("snapshot")
        StubProtocol.handler = { _ in (200, body) }
        let snap = try await api().snapshot()
        XCTAssertEqual(snap.nodes.count, 18)
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/snapshot")
    }

    func test_404_isNotFound() async {
        StubProtocol.handler = { _ in (404, Data(#"{"detail":"shipment not found"}"#.utf8)) }
        await assertAPIError(.notFound) { try await self.api().shipment(ref: "MC-00-0000") }
    }

    func test_500_isHttp() async {
        StubProtocol.handler = { _ in (500, Data()) }
        await assertAPIError(.http(500)) { try await self.api().shipment(ref: "MC-26-0412") }
    }

    func test_networkError_isOffline() async {
        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        await assertAPIError(.offline) { try await self.api().snapshot() }
    }

    func test_garbage_isDecoding() async {
        StubProtocol.handler = { _ in (200, Data("{}".utf8)) }
        do {
            _ = try await api().shipment(ref: "MC-26-0412")
            XCTFail("ожидалась ошибка")
        } catch let error as APIError {
            guard case .decoding = error else { return XCTFail("\(error)") }
        } catch {
            XCTFail("\(error)")
        }
    }

    private func assertAPIError<T>(
        _ expected: APIError, _ body: () async throws -> T, line: UInt = #line
    ) async {
        do {
            _ = try await body()
            XCTFail("ожидалась \(expected)", line: line)
        } catch {
            XCTAssertEqual(error as? APIError, expected, line: line)
        }
    }

    // MARK: часы демо

    private static let clockJSON = Data(
        #"{"now":"2026-11-01T10:00:00Z","offset_hours":6,"story_start":"2026-11-01T04:00:00Z","story_ref":"MC-26-0398"}"#.utf8)

    private static func body(_ request: URLRequest) -> [String: Any]? {
        var data = request.httpBody
        if data == nil, let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            var out = Data()
            while stream.hasBytesAvailable {
                let n = stream.read(&buffer, maxLength: buffer.count)
                if n <= 0 { break }
                out.append(buffer, count: n)
            }
            data = out
        }
        return data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
    }

    func test_demoClock_get() async throws {
        nonisolated(unsafe) var method: String?
        StubProtocol.handler = { request in
            method = request.httpMethod
            return (200, Self.clockJSON)
        }
        let state = try await api().demoClock()
        XCTAssertEqual(StubProtocol.lastPath, "/api/v1/demo/clock")
        XCTAssertEqual(method, "GET")
        XCTAssertEqual(state.offsetHours, 6)
    }

    func test_demo_advance_postsBody() async throws {
        nonisolated(unsafe) var seen: URLRequest?
        StubProtocol.handler = { request in
            seen = request
            return (200, Self.clockJSON)
        }
        _ = try await api().demo(.advance(hours: 6))
        let request = try XCTUnwrap(seen)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(Self.body(request)?["action"] as? String, "advance")
        XCTAssertEqual(Self.body(request)?["hours"] as? Double, 6)
    }

    func test_demo_nextBeat_body() async throws {
        nonisolated(unsafe) var seen: URLRequest?
        StubProtocol.handler = { request in
            seen = request
            return (200, Self.clockJSON)
        }
        _ = try await api().demo(.nextBeat)
        let body = try XCTUnwrap(Self.body(try XCTUnwrap(seen)))
        XCTAssertEqual(body["action"] as? String, "next_beat")
        XCTAssertNil(body["hours"])
    }

    func test_demo_404_isNotFound() async {
        StubProtocol.handler = { _ in (404, Data(#"{"detail":"demo clock is disabled"}"#.utf8)) }
        do {
            _ = try await api().demoClock()
            XCTFail("ожидали notFound")
        } catch {
            XCTAssertEqual(APIError.from(error), .notFound)
        }
    }
}
