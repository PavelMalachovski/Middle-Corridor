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
}
