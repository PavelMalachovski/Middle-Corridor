import Foundation

/// Хранилище токена сессии. В приложении — Keychain (не UserDefaults и не файл);
/// здесь только контракт и память для тестов.
public protocol TokenStore: Sendable {
    func load() -> String?
    /// `nil` стирает токен.
    func save(_ token: String?)
}

public final class InMemoryTokenStore: TokenStore, @unchecked Sendable {
    private let lock = NSLock()
    private var token: String?

    public init(token: String? = nil) { self.token = token }

    public func load() -> String? {
        lock.lock()
        defer { lock.unlock() }
        return token
    }

    public func save(_ token: String?) {
        lock.lock()
        defer { lock.unlock() }
        self.token = token
    }
}
