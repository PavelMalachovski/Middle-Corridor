import MCCore
import SwiftUI

enum AppTab: String, Hashable {
    case shipments, corridor
}

/// Корень: вкладки «Грузы» и «Коридор».
struct RootView: View {
    @Bindable var model: AppModel
    @Environment(\.l10n) private var l
    @Environment(\.scenePhase) private var scenePhase

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
            // ведущий: двойной тап тремя пальцами — следующий шаг демо-истории
            DemoGesture {
                guard model.demo.isActive else { return }
                Task { await model.demo.perform(.nextBeat) }
            }
        }
        .task { await model.demo.probe() }
        .task {
            // на переднем плане — обновление раз в минуту: изменения → уведомления, Live Activity
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                if scenePhase == .active { await model.store.refresh() }
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await model.store.refresh() } }
        }
    }
}
