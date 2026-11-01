import MCCore
import SwiftUI

/// Первый экран — «Мои грузы»; пока список пуст — состояние коридора.
struct MyShipmentsView: View {
    @Bindable var model: AppModel
    @Environment(\.l10n) private var l
    @State private var showAdd = false
    @State private var showSettings = false

    private var store: TrackedShipments { model.store }

    var body: some View {
        NavigationStack(path: $model.path) {
            Group {
                if store.refs.isEmpty {
                    CorridorSummaryView(store: store) { showAdd = true }
                } else {
                    list
                }
            }
            .navigationTitle(l("list.title"))
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel(l("list.settings"))
                        .accessibilityIdentifier("settings")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showAdd = true } label: { Image(systemName: "plus") }
                        .accessibilityLabel(l("add.title"))
                        .accessibilityIdentifier("add")
                }
            }
            .navigationDestination(for: String.self) { ref in
                ShipmentDetailView(ref: ref, store: store)
            }
            .refreshable { await store.refresh() }
            .task(id: model.serverURL) { await store.refresh() }
        }
        .sheet(isPresented: $showAdd) {
            AddShipmentView(store: store) { ref in
                showAdd = false
                model.path = [ref]
                Task { await model.notifier.requestAuthorizationIfNeeded() }
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView(model: model)
        }
        .alert(
            l("link.error"),
            isPresented: $model.showLinkError,
            presenting: model.linkError
        ) { _ in
            Button(l("common.ok"), role: .cancel) {}
        } message: { error in
            Text(AddShipmentView.message(for: error, l))
        }
    }

    private var list: some View {
        let labels = Labels(lang: l.lang, nodes: store.snapshot?.nodes ?? [])
        let offline = store.lastError != nil
        return List {
            if offline {
                Section { OfflineBanner(updatedAt: store.updatedAt) }
            }
            Section {
                ForEach(store.rows) { row in
                    NavigationLink(value: row.ref) {
                        ShipmentRow(
                            row: row, labels: labels, isOffline: offline,
                            isMissing: store.missing.contains(row.ref))
                    }
                    .accessibilityIdentifier("row.\(row.ref)")
                }
                .onDelete { offsets in
                    let refs = offsets.map { store.rows[$0].ref }
                    for ref in refs { store.remove(ref) }
                }
            } footer: {
                if let updated = store.updatedAt, !offline {
                    Text(l("list.updated", ["value": l.relative(updated)]))
                }
            }
        }
    }
}
