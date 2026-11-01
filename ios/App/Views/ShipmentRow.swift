import MCCore
import SwiftUI

/// Строка «Моих грузов»: номер и статус, маршрут, где сейчас (или почему стоит), прогресс и ETA.
/// `compact` — доставленные: только номер и статус.
struct ShipmentRow: View {
    let row: TrackedRow
    let labels: Labels
    let isOffline: Bool
    let isMissing: Bool
    var compact = false
    @Environment(\.l10n) private var l

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(row.ref)
                    .font(compact ? .body.monospacedDigit() : .headline.monospacedDigit())
                Spacer()
                if let shipment = row.shipment {
                    StatusPill(shipment: shipment, labels: labels)
                }
            }
            if let shipment = row.shipment {
                if !compact { details(shipment) }
            } else {
                Text(isMissing ? l("add.error.notFound") : isOffline ? l("list.noData") : l("list.loading"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, compact ? 0 : 4)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func details(_ s: Shipment) -> some View {
        let tone = Theme.tone(s.tone)
        Text(labels.route(s))
            .font(.subheadline)
            .foregroundStyle(.secondary)
        if let hold = labels.hold(s) {
            Label(hold, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline)
                .foregroundStyle(Theme.warning)
                .lineLimit(2)
        } else {
            let live = LiveStatus.make(s, labels: labels)
            Label(live.leg, systemImage: LiveStatusStyle.icon(live))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        ProgressView(value: min(max(s.progress, 0), 1))
            .tint(tone)
        HStack(spacing: 4) {
            Text(l("row.eta")).foregroundStyle(.secondary)
            Text(s.eta.map(l.dateTime) ?? "—")
                .fontWeight(.semibold)
                .monospacedDigit()
            Spacer()
            Text(l("card.progress", ["pct": String(Int((s.progress * 100).rounded()))]))
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
        .font(.caption)
    }
}
