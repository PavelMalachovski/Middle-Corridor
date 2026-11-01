import MCCore
import SwiftUI

/// Первый экран — «Мои грузы»; пока список пуст — состояние коридора.
/// Грузы — по срочности: требуют внимания → в пути → ждут отправления → доставленные.
struct MyShipmentsView: View {
    @Bindable var model: AppModel
    @Environment(\.l10n) private var l
    @State private var showAdd = false
    @State private var showSettings = false
    /// Только что удалённый груз — плашка «Отменить» на несколько секунд.
    @State private var removed: String?
    @State private var addedCount = 0

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
                ShipmentDetailView(ref: ref, store: store) { remove($0) }
            }
            .refreshable { await store.refresh() }
            .task(id: model.serverURL) { await store.refresh() }
            .safeAreaInset(edge: .bottom) {
                if let removed {
                    UndoBanner(text: l("list.removed", ["ref": removed]), action: l("list.undo")) {
                        restore(removed)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 8)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .task(id: removed) {
                guard removed != nil else { return }
                try? await Task.sleep(for: .seconds(5))
                if !Task.isCancelled { withAnimation { removed = nil } }
            }
        }
        .sensoryFeedback(.success, trigger: addedCount)
        .sheet(isPresented: $showAdd) {
            AddShipmentView(store: store) { ref in
                showAdd = false
                addedCount += 1
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
        let sections = ShipmentGroup.group(store.rows, nodes: store.snapshot?.nodes ?? [], missing: store.missing)
        return List {
            if offline {
                Section { OfflineBanner(updatedAt: store.updatedAt) }
            }
            ForEach(sections) { section in
                Section {
                    ForEach(section.rows) { row in
                        rowLink(row, labels: labels, offline: offline, compact: section.group == .delivered)
                    }
                } header: {
                    // одна секция — заголовок не нужен: список и так однородный
                    if sections.count > 1 {
                        Text(header(section.group, count: section.rows.count))
                            .accessibilityIdentifier("section.\(section.group.rawValue)")
                    }
                } footer: {
                    if section.group == sections.last?.group, let updated = store.updatedAt, !offline {
                        Text(l("list.updated", ["value": l.relative(updated)]))
                    }
                }
            }
        }
    }

    private func rowLink(_ row: TrackedRow, labels: Labels, offline: Bool, compact: Bool) -> some View {
        NavigationLink(value: row.ref) {
            ShipmentRow(
                row: row, labels: labels, isOffline: offline,
                isMissing: store.missing.contains(row.ref), compact: compact)
        }
        .accessibilityIdentifier("row.\(row.ref)")
        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
            Button(role: .destructive) { remove(row.ref) } label: {
                Label(l("list.delete"), systemImage: "trash")
            }
        }
        .contextMenu {
            if let shipment = row.shipment {
                ShareLink(
                    item: AppLinks.share(row.ref),
                    subject: Text(row.ref),
                    message: Text(AppLinks.message(shipment, labels: labels, l: l))
                ) {
                    Label(l("card.share"), systemImage: "square.and.arrow.up")
                }
            }
            Button(role: .destructive) { remove(row.ref) } label: {
                Label(l("list.delete"), systemImage: "trash")
            }
        }
    }

    private func header(_ group: ShipmentGroup, count: Int) -> String {
        switch group {
        case .attention: l("list.section.attention")
        case .active: l("list.section.active")
        case .planned: l("list.section.planned")
        case .delivered: l("list.section.delivered", ["count": String(count)])
        }
    }

    private func remove(_ ref: String) {
        if model.path.contains(ref) { model.path = [] }
        model.remove(ref)
        withAnimation { removed = ref }
    }

    /// «Отменить»: номер возвращается в список, данные — с сервера (Live Activity не восстанавливается).
    private func restore(_ ref: String) {
        withAnimation { removed = nil }
        Task { _ = try? await store.add(ref) }
    }
}

/// Плашка «Груз удалён · Отменить» над панелью вкладок.
private struct UndoBanner: View {
    let text: String
    let action: String
    let onUndo: () -> Void

    var body: some View {
        HStack {
            Text(text).font(.subheadline)
            Spacer()
            Button(action, action: onUndo)
                .font(.subheadline.weight(.semibold))
                .accessibilityIdentifier("undo")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityElement(children: .contain)
    }
}
