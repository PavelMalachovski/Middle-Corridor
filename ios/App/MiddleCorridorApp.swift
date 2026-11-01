import MCCore
import SwiftUI

@main
struct MiddleCorridorApp: App {
    @State private var model = AppModel()
    @AppStorage(LangChoice.key) private var langChoice = LangChoice.system.rawValue

    var body: some Scene {
        WindowGroup {
            let l10n = L10n(lang: (LangChoice(rawValue: langChoice) ?? .system).resolved())
            MyShipmentsView(model: model)
                .environment(\.l10n, l10n)
                .environment(\.locale, l10n.locale)
                .onOpenURL { url in
                    Task { await model.open(url) }
                }
        }
    }
}
