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
    static let refKey = "mc.widget.ref"
    static let langKey = "mc.widget.lang"
}
