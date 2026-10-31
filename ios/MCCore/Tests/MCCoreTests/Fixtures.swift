import Foundation
import XCTest
@testable import MCCore

/// Фикстуры сняты с мок-бэкенда (MOCK_DATA=true) 31.10.2026.
enum Fixture {
    static func data(_ name: String) throws -> Data {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"),
            "нет фикстуры \(name).json"
        )
        return try Data(contentsOf: url)
    }

    static func shipment(_ ref: String) throws -> Shipment {
        try APIDate.makeDecoder().decode(Shipment.self, from: data("shipment_\(ref)"))
    }

    static func snapshot() throws -> MapSnapshot {
        try APIDate.makeDecoder().decode(MapSnapshot.self, from: data("snapshot"))
    }
}
