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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver

    /// «Уменьшение движения» и VoiceOver — без анимации: после экрана запуска сразу приложение.
    private var splashVisible: Bool { model.showSplash && !reduceMotion && !voiceOver }

    var body: some View {
        TabView(selection: $model.tab) {
            MyShipmentsView(model: model)
                .tabItem {
                    Label(l("tab.shipments"), systemImage: "shippingbox").accessibilityIdentifier("tab.shipments")
                }
                .tag(AppTab.shipments)
            CorridorView(model: model)
                .tabItem {
                    Label(l("tab.corridor"), systemImage: "map").accessibilityIdentifier("tab.corridor")
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
        .overlay {
            ZStack {
                if splashVisible {
                    SplashView(hold: model.splashHold) { model.showSplash = false }
                        .transition(.opacity)
                }
            }
            .animation(.easeOut(duration: SplashTimeline.skipFade), value: splashVisible)
        }
        .onAppear {
            // включат «Уменьшение движения» позже — заставка посреди работы не всплывёт
            if reduceMotion || voiceOver { model.showSplash = false }
        }
        .task { await model.demo.probe() }
        .task {
            // на переднем плане — обновление раз в минуту: изменения → уведомления, Live Activity
            // без проверки scenePhase: в долгой задаче это копия на момент её старта (могла
            // быть не .active — и таймер молчал бы всегда); в фоне приложение и так стоит
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                if !Task.isCancelled { await model.store.refresh() }
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await model.store.refresh() } }
        }
    }
}
