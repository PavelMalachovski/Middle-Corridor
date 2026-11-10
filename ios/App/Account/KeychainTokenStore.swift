import Foundation
import MCCore
import OSLog
import Security

/// Токен сессии аккаунта — в Keychain (только это устройство, после первой разблокировки:
/// обновление по таймеру работает и при заблокированном экране). Токен не логируется.
struct KeychainTokenStore: TokenStore {
    let service: String
    let account: String

    init(service: String = "mc.account", account: String = "session") {
        self.service = service
        self.account = account
    }

    func load() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
            let data = item as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func save(_ token: String?) {
        guard let token else {
            let status = SecItemDelete(baseQuery as CFDictionary)
            if status != errSecSuccess && status != errSecItemNotFound { report("delete", status) }
            return
        }
        let data = Data(token.utf8)
        // сначала обновление: без «удалить, потом добавить» токен не пропадает, если добавление не прошло
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        var status = SecItemUpdate(baseQuery as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            let query = baseQuery.merging(attributes) { _, new in new }
            status = SecItemAdd(query as CFDictionary, nil)
        }
        if status != errSecSuccess { report("save", status) }
    }

    /// Только код ошибки Keychain — без токена.
    private func report(_ action: String, _ status: OSStatus) {
        Self.log.error("keychain \(action, privacy: .public) failed: \(status, privacy: .public)")
    }

    private static let log = Logger(subsystem: "com.malakhouski.mcstatus", category: "account")

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
