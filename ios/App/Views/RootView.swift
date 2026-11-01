import MCCore
import SwiftUI

enum AppTab: String, Hashable {
    case shipments, corridor
}

/// Корень: вкладки «Грузы» и «Коридор».
struct RootView: View {
    @Bindable var model: AppModel
    @Environment(\.l10n) private var l

    var body: some View {
        TabView(selection: $model.tab) {
            MyShipmentsView(model: model)
                .tabItem {
                    Label(l("tab.shipments"), systemImage: "shippingbox").accessibilityIdentifier("tab.shipments")
                }
                .tag(AppTab.shipments)
            CorridorView(store: model.store)
                .tabItem {
                    Label(l("tab.corridor"), systemImage: "wind").accessibilityIdentifier("tab.corridor")
                }
                .tag(AppTab.corridor)
        }
        .background {
            // ведущий: долгое нажатие двумя пальцами — следующий шаг демо-истории
            DemoGesture {
                guard model.demo.isActive else { return }
                Task { await model.demo.perform(.nextBeat) }
            }
        }
        .task { await model.demo.probe() }
    }
}
