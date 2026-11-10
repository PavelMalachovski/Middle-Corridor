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
    /// Приглашения, отправленные в этой сессии, по компаниям: сервер отдаёт только принявших.
    private(set) var invitations: [Int: [PendingInvite]] = [:]

    /// Грузы обновились (было → стало): локальные уведомления (`AppModel`).
    @ObservationIgnored var onShipmentsChange: ((_ old: [MyShipment], _ new: [MyShipment]) -> Void)?

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
    /// `notify: false` — после своего действия (событие, правка): о нём не уведомляем самого себя.
    func refresh(notify: Bool = true) async {
        guard isSignedIn else { return }
        let started = generation
        do {
            async let me = api.me()
            async let shipments = api.myShipments()
            let (newMe, newShipments) = try await (me, shipments)
            guard started == generation else { return }
            let old = self.shipments
            self.me = newMe
            self.shipments = newShipments
            lastError = nil
            if notify { onShipmentsChange?(old, newShipments) }
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

    // MARK: - Действия (после каждого — список заново, без уведомления о своём же действии)

    /// Компании, где можно создать груз; пусто — «Новый груз» не показываем.
    var creatableOrgs: [MembershipInfo] { AccountAccess.creatableOrgs(me) }
    /// Компании, где можно смотреть команду и приглашать.
    var managedOrgs: [MembershipInfo] { AccountAccess.managedOrgs(me) }

    func create(_ shipment: NewShipment) async throws -> MyShipment {
        let created = try await api.create(shipment)
        await refresh(notify: false)
        return created
    }

    func update(ref: String, _ patch: ShipmentPatch) async throws {
        _ = try await api.update(ref: ref, patch)
        await refresh(notify: false)
    }

    func addEvent(ref: String, _ event: CheckpointEventInput) async throws {
        _ = try await api.addEvent(ref: ref, event)
        await refresh(notify: false)
    }

    func share(ref: String, orgId: Int) async throws { try await api.share(ref: ref, orgId: orgId) }
    func clients(orgId: Int) async throws -> [OrgSummary] { try await api.clients(orgId: orgId) }
    func members(orgId: Int) async throws -> [OrgMember] { try await api.members(orgId: orgId) }
    func revoke(orgId: Int, userId: Int) async throws { try await api.revoke(orgId: orgId, userId: userId) }

    /// Приглашение; ответ `mail` — ушло ли письмо (приглашение создано в любом случае).
    func invite(orgId: Int, email: String, role: AccountRole, nodeCodes: [String]) async throws -> Invitation {
        let email = Self.normalize(email)
        let result = try await api.invite(orgId: orgId, email: email, role: role, nodeCodes: nodeCodes)
        var list = invitations[orgId, default: []].filter { $0.email != email }
        list.append(PendingInvite(email: email, role: role, nodeCodes: nodeCodes, mailSent: result.mailSent))
        invitations[orgId] = list
        return result
    }

    /// Устройство зарегистрировано для push: о событиях скажет сервер.
    func registerDevice(token: String, environment: String) async throws {
        try await api.registerDevice(apnsToken: token, environment: environment)
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
        invitations = [:]
    }

    static func normalize(_ email: String) -> String {
        email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}

/// Приглашение этой сессии — в «Команде» до первого входа приглашённого.
struct PendingInvite: Hashable, Identifiable {
    let email: String
    let role: AccountRole
    let nodeCodes: [String]
    let mailSent: Bool
    var id: String { email }
}
