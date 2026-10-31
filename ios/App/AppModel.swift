import Foundation
import MCCore
import Observation

/// Состояние приложения: адрес сервера, «Мои грузы», навигация и открытие ссылок.
@MainActor
@Observable
final class AppModel {
    static let serverKey = "mc.server"
    static let defaultServer = "http://localhost:8000"

    private(set) var store: TrackedShipments
    private(set) var serverURL: String
    var path: [String] = []
    var linkError: AddError?
    var showLinkError: Bool {
        get { linkError != nil }
        set { if !newValue { linkError = nil } }
    }

    /// UI-тесты и демо без бэкенда: `-mc-fake-api` (только Debug).
    let isFake: Bool
    private let storage: any RefStorage
    private let defaults: UserDefaults

    init(arguments: [String] = ProcessInfo.processInfo.arguments, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        isFake = arguments.contains("-mc-fake-api")
        // serverURL под @Observable — вычисляемое свойство: читать его до инициализации store нельзя
        let server = defaults.string(forKey: Self.serverKey) ?? Self.defaultServer
        serverURL = server
        storage = isFake ? MemoryRefStorage() : UserDefaultsRefStorage()
        store = TrackedShipments(api: Self.makeAPI(fake: isFake, server: server), storage: storage)
    }

    /// Меняет сервер: список номеров сохраняется, данные перезагрузятся с нового адреса.
    func setServer(_ input: String) {
        let normalized = Self.normalize(input)
        guard normalized != serverURL, URL(string: normalized) != nil else { return }
        serverURL = normalized
        defaults.set(normalized, forKey: Self.serverKey)
        store = TrackedShipments(api: Self.makeAPI(fake: isFake, server: normalized), storage: storage)
    }

    /// Проверка адреса из настроек: число узлов коридора или ошибка.
    func probe(_ input: String) async -> Result<Int, APIError> {
        let api = Self.makeAPI(fake: isFake, server: Self.normalize(input))
        do {
            return .success(try await api.snapshot().nodes.count)
        } catch {
            return .failure(APIError.from(error))
        }
    }

    /// `mcstatus://s/<номер>` или `https://…/?s=<номер>` → груз в списке и открыт.
    func open(_ url: URL) async {
        guard let ref = ShipmentRef.from(url: url) else { return }
        do {
            let added = try await store.add(ref)
            path = [added]
            // номер уже был в списке, но данных нет (старт без сети) — дозапросить
            if store.shipments[added] == nil { await store.refresh() }
        } catch {
            linkError = (error as? AddError) ?? .server
        }
    }

    static func normalize(_ input: String) -> String {
        var s = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return defaultServer }
        if !s.contains("://") { s = "http://" + s }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    private static func makeAPI(fake: Bool, server: String) -> any CorridorAPI {
        #if DEBUG
            if fake { return FakeCorridorAPI() }
        #endif
        return HTTPCorridorAPI(baseURL: URL(string: server) ?? URL(string: defaultServer)!)
    }
}
