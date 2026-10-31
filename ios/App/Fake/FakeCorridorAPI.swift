#if DEBUG
    import Foundation
    import MCCore

    /// Данные мок-бэкенда, вшитые в приложение (`snapshot.json` из фикстур MCCore):
    /// UI-тесты и показ без Мака. Запуск с аргументом `-mc-fake-api`.
    struct FakeCorridorAPI: CorridorAPI {
        func snapshot() async throws -> MapSnapshot {
            try Self.load()
        }

        func shipment(ref: String) async throws -> Shipment {
            try await Task.sleep(for: .milliseconds(200))
            guard let shipment = try Self.load().shipments.first(where: { $0.ref == ref }) else {
                throw APIError.notFound
            }
            return shipment
        }

        private static func load() throws -> MapSnapshot {
            guard let url = Bundle.main.url(forResource: "snapshot", withExtension: "json") else {
                throw APIError.http(500)
            }
            return try APIDate.makeDecoder().decode(MapSnapshot.self, from: Data(contentsOf: url))
        }
    }
#endif
