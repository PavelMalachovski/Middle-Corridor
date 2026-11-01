import MCCore
import SwiftUI

@main
struct MiddleCorridorApp: App {
    @State private var model = AppModel()
    @AppStorage(LangChoice.key) private var langChoice = LangChoice.system.rawValue

    var body: some Scene {
        WindowGroup {
            let l10n = L10n(lang: (LangChoice(rawValue: langChoice) ?? .system).resolved())
            RootView(model: model)
                .preferredColorScheme(Self.forcedScheme)
                .environment(\.l10n, l10n)
                .environment(\.locale, l10n.locale)
                .onOpenURL { url in
                    Task { await model.open(url) }
                }
        }
    }

    /// Скриншоты тёмной темы в UI-тестах: `-mc-appearance dark` (смена темы через simctl
    /// до приложения на этом симуляторе не доходит). В Release — всегда как в системе.
    private static var forcedScheme: ColorScheme? {
        #if DEBUG
            switch UserDefaults.standard.string(forKey: "mc-appearance") {
            case "dark": return .dark
            case "light": return .light
            default: return nil
            }
        #else
            return nil
        #endif
    }
}
