import MCCore
import SwiftUI

/// Карточка груза: карта маршрута, где сейчас, очередь, погода в порту, ETA, точки маршрута.
struct ShipmentDetailView: View {
    let ref: String
    let store: TrackedShipments
    @Environment(\.l10n) private var l

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
        let position = labels.position(s)
        return List {
            Section {
                RouteMapView(shipment: s)
                    .listRowInsets(EdgeInsets())
            }
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text(labels.cargo(s)).font(.headline)
                    Text(labels.route(s)).foregroundStyle(.secondary)
                    HStack {
                        StatusPill(shipment: s, labels: labels)
                        Spacer()
                        Text(l("card.progress", ["pct": String(Int((s.progress * 100).rounded()))]))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    ProgressView(value: min(max(s.progress, 0), 1))
                        .tint(Theme.tone(s.tone))
                }
                .padding(.vertical, 4)
            }

            Section(l("card.now")) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(position.title)
                        .italic(!position.confirmed)
                        .foregroundStyle(position.confirmed ? .primary : .secondary)
                        .accessibilityIdentifier("card.position")
                    Text(position.detail)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let hold = labels.hold(s) {
                    Label(hold, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(Theme.warning)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("hold")
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(l("card.lastEvent")).font(.caption).foregroundStyle(.secondary)
                    Text(labels.event(s)).accessibilityIdentifier("card.event")
                    if let at = s.lastEventAt {
                        Text(l.dateTime(at)).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }

            if let queue = s.queue {
                QueueSection(queue: queue, labels: labels)
            }
            if let snapshot = store.snapshot,
                let port = RouteGeometry.weatherPort(for: s, nodes: snapshot.nodes)
            {
                PortWeatherSection(port: port, snapshot: snapshot, labels: labels)
            }

            Section {
                LabeledContent(l("card.eta"), value: s.eta.map(l.dateTime) ?? "—")
                if s.isDelayed {
                    LabeledContent(l("card.delay")) {
                        Text("+\(l.hours(s.delayHours))").foregroundStyle(Theme.warning)
                    }
                }
                LabeledContent(l("card.client"), value: s.client)
            }

            Section(l("card.route")) {
                ForEach(Array(s.checkpoints.enumerated()), id: \.offset) { _, checkpoint in
                    CheckpointRow(checkpoint: checkpoint, name: labels.checkpoint(checkpoint))
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                ShareLink(
                    item: URL(string: "mcstatus://s/\(s.ref)")!,
                    subject: Text(s.ref),
                    message: Text("\(s.ref) · \(labels.route(s)) · \(labels.state(s))")
                ) {
                    Image(systemName: "square.and.arrow.up")
                }
                .accessibilityLabel(l("card.share"))
            }
        }
    }
}

/// Точка маршрута: ✓ пройдена, ● сейчас, ○ впереди; факт или план.
private struct CheckpointRow: View {
    let checkpoint: Checkpoint
    let name: String
    @Environment(\.l10n) private var l

    var body: some View {
        HStack(spacing: 12) {
            icon.frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .fontWeight(checkpoint.state.known == .current ? .semibold : .regular)
                Text(time)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let late = lateHours, late >= 1 {
                Text("+\(l.hours(late))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.warning)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var icon: some View {
        switch checkpoint.state.known {
        case .done: Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.ok)
        case .current: Image(systemName: "circle.inset.filled").foregroundStyle(Theme.accent)
        case .planned, nil: Image(systemName: "circle").foregroundStyle(.secondary)
        }
    }

    private var time: String {
        if let actual = checkpoint.actualAt {
            return l("card.fact", ["ts": l.dateTime(actual)])
        }
        return l("card.plan", ["ts": l.dateTime(checkpoint.plannedAt)])
    }

    private var lateHours: Double? {
        checkpoint.actualAt.map { $0.timeIntervalSince(checkpoint.plannedAt) / 3600 }
    }
}
