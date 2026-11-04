import Foundation

/// Адрес бэкенда по умолчанию — ключ сборки `MC_API_BASE_URL` (project.yml → Info.plist
/// `MCAPIBaseURL`, свой у приложения и у виджета). Debug — демо-бэкенд на Маке
/// (`http://localhost:8000`, симулятор), Release — боевой API на Vercel. Адрес, введённый в
/// настройках приложения или виджета, важнее.
enum BackendConfig {
    static let infoKey = "MCAPIBaseURL"
    /// Ключ не подставился (сборка мимо project.yml) — локальный демо-бэкенд, как раньше.
    static let fallback = "http://localhost:8000"

    static let defaultServer = resolve(Bundle.main.object(forInfoDictionaryKey: infoKey) as? String)

    /// Пустое значение или не http(s) — `fallback`; хвостовые `/` срезаются.
    static func resolve(_ raw: String?) -> String {
        guard var s = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
            let url = URL(string: s), url.host != nil,
            let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http"
        else { return fallback }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }
}
