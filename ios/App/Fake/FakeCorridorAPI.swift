#if DEBUG
    import Foundation
    import MCCore

    /// Данные мок-бэкенда, вшитые в приложение (`snapshot.json` из фикстур MCCore):
    /// UI-тесты и показ без Мака. Запуск с аргументом `-mc-fake-api`.
    struct FakeCorridorAPI: CorridorAPI {
        private let clock = FakeDemoClock()

        /// Пульт для UI-теста: сдвиг считается, данные фикстур не меняются.
        func demoClock() async throws -> DemoClockState {
            await clock.state(base: try Self.load().generatedAt)
        }

        func demo(_ action: DemoAction) async throws -> DemoClockState {
            await clock.apply(action)
            return try await demoClock()
        }

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

    private actor FakeDemoClock {
        private var offset = 0.0

        func apply(_ action: DemoAction) {
            switch action {
            case .advance(let hours): offset += hours
            case .nextBeat: offset += 6
            case .reset: offset = 0
            }
        }

        func state(base: Date) -> DemoClockState {
            DemoClockState(
                now: base.addingTimeInterval(offset * 3600), offsetHours: offset, storyStart: base,
                storyRef: "MC-26-0398")
        }
    }
#endif
