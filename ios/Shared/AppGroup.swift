import Foundation

/// Общий контейнер приложения и виджета. Есть только в сборках под симулятор (entitlements
/// `*.sim.entitlements`): бесплатный Apple ID на iPhone App Groups не подписывает — там виджет
/// настраивается номером и адресом сервера сам.
enum AppGroup {
    static let id = "group.com.malakhouski.mcstatus"

    static var container: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: id)
    }

    /// nil, если контейнера нет (iPhone с Personal Team).
    static var defaults: UserDefaults? {
        container == nil ? nil : UserDefaults(suiteName: id)
    }

    static let serverKey = "mc.server"
    /// Сервер по умолчанию — публичный демо-бэкенд на Vercel (MOCK_DATA, пульт демо выключен):
    /// приложение работает без Мака. Свой бэкенд с пультом — в скрытом разделе настроек.
    static let defaultServer = "https://middle-corridor-weld.vercel.app"
    static let refKey = "mc.widget.ref"
    static let langKey = "mc.widget.lang"
}
