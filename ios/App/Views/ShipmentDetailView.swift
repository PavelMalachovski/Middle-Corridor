import MCCore
import SwiftUI

/// Карточка груза — от ответа к подробностям: статус и ETA, где сейчас и почему стоит, очередь;
/// почему задержка; Live Activity; карта (нажатие — на весь экран); погода в порту; лента маршрута; груз и клиент.
/// Груз аккаунта (`accountKey` — ключ `AccountRows`) берётся только из `account`, даже если такой же
/// номер отслеживается как демо: без Live Activity, «Поделиться» и «Удалить» — он приходит с сервера
/// аккаунтов и на сайте не открывается.
struct ShipmentDetailView: View {
    let ref: String
    let store: TrackedShipments
    let account: AccountModel?
    let accountKey: String?
    /// «Удалить из списка» из меню «…»: удаляет и закрывает карточку.
    let onRemove: (String) -> Void
    @Environment(\.l10n) private var l

    var body: some View {
        Group {
            if let accountKey {
                if let mine = account?.shipment(key: accountKey) {
                    content(mine.shipment, labels: labels, owned: true)
                } else {
                    ContentUnavailableView(l("card.missing"), systemImage: "shippingbox")  // вышли из аккаунта
                }
            } else if let shipment = store.shipments[ref] {
                content(shipment, labels: labels, owned: false)
            } else if store.missing.contains(ref) {
                ContentUnavailableView(l("add.error.notFound"), systemImage: "shippingbox")
            } else if store.lastError != nil {
                ContentUnavailableView(l("list.noData"), systemImage: "wifi.slash")
            } else if store.refs.contains(ref) {
                ProgressView()
            } else {
                ContentUnavailableView(l("card.missing"), systemImage: "shippingbox")
            }
        }
        .navigationTitle(ref)
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            if let account, accountKey != nil {
                await account.refresh()
            } else {
                await store.refresh()
            }
        }
    }

    private var labels: Labels { Labels(lang: l.lang, nodes: store.snapshot?.nodes ?? []) }

    /// `owned` — груз аккаунта.
    private func content(_ s: Shipment, labels: Labels, owned: Bool) -> some View {
        let nodes = store.snapshot?.nodes ?? []
        return List {
            ShipmentHeroSection(shipment: s, labels: labels)

            if s.isDelayed, let parts = s.delayBreakdown, !parts.isEmpty {
                DelaySection(parts: parts, labels: labels)
            }

            // санкции, требующие внимания, — сразу под главным; «чисто» и «ждём лист» — внизу
            if let check = s.sanctions, SanctionsSection.needsAttention(check) {
                SanctionsSection(check: check, labels: labels)
            }

            if LiveActivities.enabled, !owned {
                Section {
                    LiveActivityButton(shipment: s, labels: labels)
                }
            }

            Section {
                // превью неподвижно (жесты спорят с прокруткой); нажатие — полноэкранная карта
                RouteMapView(shipment: s, nodes: nodes)
                    .listRowInsets(EdgeInsets())
            }

            if let snapshot = store.snapshot,
                let port = RouteGeometry.weatherPort(for: s, nodes: snapshot.nodes)
            {
                PortWeatherSection(port: port, snapshot: snapshot, labels: labels)
            }

            CheckpointTimelineSection(shipment: s, labels: labels)

            if let check = s.sanctions, !SanctionsSection.needsAttention(check) {
                SanctionsSection(check: check, labels: labels)
            }

            if let cargo = s.cargoDetails {
                CargoSection(cargo: cargo, lang: labels.lang)
            }

            Section(l("card.details")) {
                LabeledContent(l("card.cargo"), value: labels.cargo(s))
                LabeledContent(l("card.client"), value: s.client)
            }
        }
        .toolbar {
            if !owned {
                ToolbarItem(placement: .topBarTrailing) { menu(s, labels: labels) }
            }
        }
    }

    private func menu(_ s: Shipment, labels: Labels) -> some View {
        Menu {
            ShareLink(
                item: AppLinks.share(s.ref),
                subject: Text(s.ref),
                message: Text(AppLinks.message(s, labels: labels, l: l))
            ) {
                Label(l("card.share"), systemImage: "square.and.arrow.up")
            }
            Button(role: .destructive) { onRemove(s.ref) } label: {
                Label(l("card.remove"), systemImage: "trash")
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .accessibilityLabel(l("card.actions"))
        .accessibilityIdentifier("card.menu")
    }
}

/// «На экран блокировки» / «Убрать с экрана блокировки» — Live Activity этого груза.
private struct LiveActivityButton: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l
    @State private var isActive = false

    var body: some View {
        Button {
            Task {
                if isActive {
                    await LiveActivities.stop(shipment.ref)
                } else {
                    try? LiveActivities.start(shipment, labels: labels)
                    AppGroup.defaults?.set(shipment.ref, forKey: AppGroup.refKey)  // виджет — тот же груз
                }
                isActive = LiveActivities.isActive(shipment.ref)
            }
        } label: {
            Label(
                l(isActive ? "card.liveActivity.stop" : "card.liveActivity.start"),
                systemImage: isActive ? "lock.slash" : "lock.iphone")
        }
        .sensoryFeedback(.success, trigger: isActive) { _, new in new }
        .accessibilityIdentifier("card.liveActivity")
        .onAppear { isActive = LiveActivities.isActive(shipment.ref) }
    }
}
