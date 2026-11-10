import Foundation
import MCCore
import Observation
import WidgetKit

/// Состояние приложения: адрес сервера, «Мои грузы», навигация и открытие ссылок.
@MainActor
@Observable
final class AppModel {
    static let serverKey = "mc.server"
    static let splashKey = "mc.splash"
    static let defaultServer = AppGroup.defaultServer

    private(set) var store: TrackedShipments
    /// Клиент текущего сервера (данные — через store, часы демо — через demo).
    private(set) var api: any CorridorAPI
    /// Аккаунт (вход по коду, грузы компаний); `nil` — сервер аккаунтов в сборке не задан.
    let account: AccountModel?
    /// Пульт ведущего (скрыт; включается долгим нажатием на версию в настройках).
    @ObservationIgnored lazy var demo = DemoController(model: self, defaults: defaults)
    @ObservationIgnored let notifier = Notifier()
    private(set) var serverURL: String
    var path: [String] = []
    var tab: AppTab = .shipments
    /// Точность прогноза за 90 дней (вкладка «Коридор»); нет ответа — блок скрыт.
    private(set) var accuracy: AccuracyReport?
    var linkError: AddError?
    var showLinkError: Bool {
        get { linkError != nil }
        set { if !newValue { linkError = nil } }
    }

    /// Заставка «Переправа» — только при холодном старте (живёт, пока жив процесс).
    /// `-mc.splash NO` — без неё (UI-тесты); открытие груза по ссылке/уведомлению её снимает.
    var showSplash: Bool
    /// `-mc.splash hold` (только Debug): заставка замирает на полном кадре до тапа.
    let splashHold: Bool
    /// UI-тесты и демо без бэкенда: `-mc-fake-api` (только Debug).
    let isFake: Bool
    private let storage: any RefStorage
    private let cache: any ShipmentCache
    private let defaults: UserDefaults

    init(arguments: [String] = ProcessInfo.processInfo.arguments, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        isFake = arguments.contains("-mc-fake-api")
        let splash = defaults.string(forKey: Self.splashKey)?.lowercased() ?? ""
        showSplash = !["no", "false", "0"].contains(splash)
        #if DEBUG
            splashHold = splash == "hold"
        #else
            splashHold = false
        #endif
        // serverURL под @Observable — вычисляемое свойство: читать его до инициализации store нельзя
        let server = defaults.string(forKey: Self.serverKey) ?? Self.defaultServer
        serverURL = server
        storage = isFake ? MemoryRefStorage() : UserDefaultsRefStorage()
        cache = isFake ? MemoryShipmentCache() : FileShipmentCache(directory: Self.cacheDirectory)
        AppGroup.defaults?.set(server, forKey: AppGroup.serverKey)
        let api = Self.makeAPI(fake: isFake, server: server)
        self.api = api
        store = TrackedShipments(api: api, storage: storage, cache: cache, server: server)
        account = Self.makeAccount(fake: isFake)
        observe(store)
        notifier.onOpen = { [weak self] ref in self?.show(ref) }
    }

    /// Меняет сервер: список номеров сохраняется, данные перезагрузятся с нового адреса.
    func setServer(_ input: String) {
        let normalized = Self.normalize(input)
        guard normalized != serverURL, URL(string: normalized) != nil else { return }
        serverURL = normalized
        defaults.set(normalized, forKey: Self.serverKey)
        accuracy = nil  // точность прежнего сервера (например, демо-синтетика) не показываем
        AppGroup.defaults?.set(normalized, forKey: AppGroup.serverKey)
        api = Self.makeAPI(fake: isFake, server: normalized)
        store = TrackedShipments(api: api, storage: storage, cache: cache, server: normalized)
        observe(store)
        Task { await demo.probe() }
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
        showSplash = false  // открыли груз — сразу к нему, без заставки
        tab = .shipments  // ошибку ссылки показывает экран «Грузы» — он должен быть открыт
        do {
            let added = try await store.add(ref)
            path = [added]
            await notifier.requestAuthorizationIfNeeded()
            // номер уже был в списке, но данных нет (старт без сети) — дозапросить
            if store.shipments[added] == nil { await store.refresh() }
        } catch {
            linkError = error  // add — typed throws(AddError)
        }
    }

    func loadAccuracy() async {
        if let report = try? await api.accuracy(days: 90) { accuracy = report }
    }

    /// Удалить груз из списка — и его Live Activity, и «груз виджета», если это он.
    func remove(_ ref: String) {
        store.remove(ref)
        Task { await LiveActivities.stop(ref) }
        if AppGroup.defaults?.string(forKey: AppGroup.refKey) == ref {
            AppGroup.defaults?.removeObject(forKey: AppGroup.refKey)
        }
    }

    /// Нажатие на уведомление, виджет или Live Activity: карточка этого груза.
    func show(_ ref: String) {
        showSplash = false
        tab = .shipments
        if store.refs.contains(ref) {
            path = [ref]
        } else if let url = URL(string: "mcstatus://s/\(ref)") {
            Task { await open(url) }
        }
    }

    /// После каждого обновления: что изменилось → уведомления и Live Activity.
    private func observe(_ store: TrackedShipments) {
        store.onChange = { [weak self] change in self?.handle(change) }
        store.onAdded = { [weak self] shipment in self?.handleAdded(shipment) }
    }

    private func handle(_ change: StoreChange) {
        let lang = (LangChoice(rawValue: defaults.string(forKey: LangChoice.key) ?? "") ?? .system).resolved()
        let labels = Labels(lang: lang, nodes: change.newNodes)
        let settings = NotifyPrefs.load(defaults)
        let sanctions = NotificationRules.sanctions(
            Array(change.newShipments.values), sent: NotifyPrefs.loadSent(defaults), settings: settings, labels: labels)
        let notices = NotificationRules.merge(sanctions + NotificationRules.diff(
            old: change.oldShipments, new: change.newShipments,
            oldNodes: change.oldNodes, newNodes: change.newNodes,
            settings: settings, labels: labels))
        notifier.deliver(notices, after: notifyDelay)
        recordSent(sanctions)
        Task { await LiveActivities.update(change.newShipments, labels: labels) }
        if let shared = AppGroup.defaults {  // виджет на симуляторе: язык и груз по умолчанию
            shared.set(lang.rawValue, forKey: AppGroup.langKey)
            if shared.string(forKey: AppGroup.refKey) == nil, let first = store.refs.first {
                shared.set(first, forKey: AppGroup.refKey)
            }
        }
        WidgetCenter.shared.reloadAllTimelines()
    }

    /// Груз только что добавили: флаг санкций — сразу, не дожидаясь обновления по таймеру.
    private func handleAdded(_ shipment: Shipment) {
        let lang = (LangChoice(rawValue: defaults.string(forKey: LangChoice.key) ?? "") ?? .system).resolved()
        let labels = Labels(lang: lang, nodes: store.snapshot?.nodes ?? [])
        let notices = NotificationRules.sanctions(
            [shipment], sent: NotifyPrefs.loadSent(defaults), settings: NotifyPrefs.load(defaults), labels: labels)
        notifier.deliver(notices, after: notifyDelay)
        recordSent(notices)
    }

    private var notifyDelay: TimeInterval { demo.isActive ? TimeInterval(demo.notifyDelay) : 0 }

    /// Отправленным помечаем, только если iOS разрешает уведомления: пока висит системный запрос
    /// (первый добавленный груз), баннер не показан — придёт на следующем обновлении.
    private func recordSent(_ notices: [AppNotice]) {
        guard !notices.isEmpty else { return }
        let ids = notices.map(\.id)
        let defaults = self.defaults
        Task { [notifier] in
            if await notifier.isAuthorized() { NotifyPrefs.recordSent(ids, defaults) }
        }
    }

    /// Офлайн-кэш: в контейнере App Group (его читает виджет), а без него — Application Support.
    static var cacheDirectory: URL {
        (AppGroup.container ?? URL.applicationSupportDirectory)
            .appending(path: "cache", directoryHint: .isDirectory)
    }

    static func normalize(_ input: String) -> String {
        var s = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return defaultServer }
        if !s.contains("://") { s = "http://" + s }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// Обновление по таймеру и при возврате в приложение: коридор и грузы аккаунта.
    func refreshAll() async {
        async let local: Void = store.refresh()
        if let account { await account.refresh() }
        await local
    }

    /// Сервер аккаунтов — ключ сборки `MC_ACCOUNT_API_URL` (Info.plist `MCAccountAPIURL`), не адрес
    /// демо из настроек: карта и демо-номера — публичный сервер, аккаунты — свой (Railway).
    /// В `-mc-fake-api` — фейк с токеном в памяти: UI-тесты не делят сессию через Keychain.
    private static func makeAccount(fake: Bool) -> AccountModel? {
        #if DEBUG
            if fake {
                let tokens = InMemoryTokenStore()
                return AccountModel(api: FakeAccountAPI(tokens: tokens), tokens: tokens)
            }
        #endif
        let raw = (Bundle.main.object(forInfoDictionaryKey: "MCAccountAPIURL") as? String ?? "")
            .trimmingCharacters(in: .whitespaces)
        // только полный адрес: «localhost:8000» URL примет со схемой «localhost» — такой не годится
        guard let url = URL(string: raw), ["http", "https"].contains(url.scheme?.lowercased()), url.host != nil
        else { return nil }
        let tokens = KeychainTokenStore()
        return AccountModel(api: HTTPAccountAPI(baseURL: url, tokens: tokens), tokens: tokens)
    }

    private static func makeAPI(fake: Bool, server: String) -> any CorridorAPI {
        #if DEBUG
            if fake { return FakeCorridorAPI() }
        #endif
        return HTTPCorridorAPI(baseURL: URL(string: server) ?? URL(string: defaultServer)!)
    }
}
