import Foundation
import MCCore
import Observation

/// Аккаунт на сервере аккаунтов (`MC_ACCOUNT_API_URL`): вход по коду, «кто я» и грузы компаний.
/// Грузы аккаунта живут только здесь — не в локальном списке номеров, виджете и Live Activity.
@MainActor
@Observable
final class AccountModel {
    private(set) var me: Me?
    private(set) var shipments: [MyShipment] = []
    /// Токен есть (вход выполнен), даже если `me` ещё не загрузился (старт без сети).
    private(set) var isSignedIn: Bool
    /// Сервер не принял сессию — вышли сами; в настройках одна строка «войдите снова».
    private(set) var sessionExpired = false
    /// Ошибка последнего обновления; прежние данные остаются на экране.
    private(set) var lastError: APIError?

    @ObservationIgnored private let api: any AccountAPI
    /// Растёт при входе и выходе: ответ, начатый до них, уже не применяется.
    @ObservationIgnored private var generation = 0

    init(api: any AccountAPI, tokens: any TokenStore) {
        self.api = api
        isSignedIn = tokens.load() != nil
    }

    /// Письмо с кодом. Ответ одинаков для любого адреса — что адрес не приглашён, не узнать.
    func requestCode(email: String) async throws {
        try await api.requestCode(email: Self.normalize(email))
    }

    /// Код из письма → сессия (токен — в Keychain) → грузы.
    func verify(email: String, code: String, deviceName: String) async throws {
        let result = try await api.verify(email: Self.normalize(email), code: code, deviceName: deviceName)
        generation += 1
        me = result.me
        isSignedIn = true
        sessionExpired = false
        lastError = nil
        await refresh()
    }

    /// Раз в минуту на переднем плане, при возврате в приложение и после входа.
    func refresh() async {
        guard isSignedIn else { return }
        let started = generation
        do {
            async let me = api.me()
            async let shipments = api.myShipments()
            let (newMe, newShipments) = try await (me, shipments)
            guard started == generation else { return }
            self.me = newMe
            self.shipments = newShipments
            lastError = nil
        } catch {
            guard started == generation else { return }
            let error = APIError.from(error)
            if error == .unauthorized {
                clear()
                sessionExpired = true
            } else {
                lastError = error
            }
        }
    }

    /// «Выйти»: экран — сразу; сервер забывает сессию следом (токен клиент стирает и без сети).
    func logout() async {
        clear()
        sessionExpired = false
        try? await api.logout()
    }

    /// Груз по ключу строки `AccountRows.key` (компания + номер).
    func shipment(key: String) -> MyShipment? {
        AccountRows.find(key, in: shipments)
    }

    /// Название компании груза для бейджа — из членств пользователя.
    func orgName(_ shipment: MyShipment) -> String? {
        me?.memberships.first { $0.orgId == shipment.orgId }?.orgName
    }

    private func clear() {
        generation += 1
        me = nil
        shipments = []
        isSignedIn = false
        lastError = nil
    }

    static func normalize(_ email: String) -> String {
        email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}
