import MCCore
import SwiftUI

/// Карточка груза — от ответа к подробностям: статус и ETA, где сейчас и почему стоит, очередь;
/// Live Activity; карта (нажатие — на весь экран); погода в порту; лента маршрута; груз и клиент.
struct ShipmentDetailView: View {
    let ref: String
    let store: TrackedShipments
    /// «Удалить из списка» из меню «…»: удаляет и закрывает карточку.
    let onRemove: (String) -> Void
    @Environment(\.l10n) private var l
    @State private var showMap = false

    var body: some View {
        Group {
            if let shipment = store.shipments[ref] {
                content(shipment, labels: Labels(lang: l.lang, nodes: store.snapshot?.nodes ?? []))
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
        .refreshable { await store.refresh() }
    }

    private func content(_ s: Shipment, labels: Labels) -> some View {
        let nodes = store.snapshot?.nodes ?? []
        return List {
            ShipmentHeroSection(shipment: s, labels: labels)

            if LiveActivities.enabled {
                Section {
                    LiveActivityButton(shipment: s, labels: labels)
                }
            }

            Section {
                // карта в списке не двигается (жесты спорят с прокруткой) — нажатие открывает её целиком
                RouteMapView(shipment: s, nodes: nodes)
                    .accessibilityLabel(mapLabel(s, labels: labels))
                    .accessibilityAddTraits(.isButton)
                    .accessibilityHint(l("card.openMap"))
                    .accessibilityAction { showMap = true }
                    .overlay {
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { showMap = true }
                    }
                    .overlay(alignment: .bottomTrailing) {
                        Label(l("card.openMap"), systemImage: "arrow.up.left.and.arrow.down.right")
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(.regularMaterial, in: Capsule())
                            .padding(10)
                            .allowsHitTesting(false)
                            .accessibilityHidden(true)
                    }
                    .listRowInsets(EdgeInsets())
            }

            if let snapshot = store.snapshot,
                let port = RouteGeometry.weatherPort(for: s, nodes: snapshot.nodes)
            {
                PortWeatherSection(port: port, snapshot: snapshot, labels: labels)
            }

            CheckpointTimelineSection(shipment: s, labels: labels)

            Section(l("card.details")) {
                LabeledContent(l("card.cargo"), value: labels.cargo(s))
                LabeledContent(l("card.client"), value: s.client)
            }
        }
        .fullScreenCover(isPresented: $showMap) {
            RouteMapScreen(shipment: s, nodes: nodes)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
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
    }

    /// Карта для VoiceOver — смыслом, а не «карта маршрута».
    private func mapLabel(_ s: Shipment, labels: Labels) -> String {
        l("card.mapLabel.value", [
            "where": labels.position(s).title,
            "pct": String(Int((s.progress * 100).rounded())),
        ])
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
