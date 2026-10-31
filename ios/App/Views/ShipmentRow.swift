import MCCore
import SwiftUI

/// Строка «Моих грузов»: номер, статус, маршрут, прогресс.
struct ShipmentRow: View {
    let row: TrackedRow
    let labels: Labels
    let isOffline: Bool
    @Environment(\.l10n) private var l

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(row.ref)
                    .font(.headline.monospacedDigit())
                Spacer()
                if let shipment = row.shipment {
                    StatusPill(shipment: shipment, labels: labels)
                }
            }
            if let shipment = row.shipment {
                Text(labels.route(shipment))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                ProgressView(value: min(max(shipment.progress, 0), 1))
                    .tint(Theme.tone(shipment.tone))
            } else {
                Text(isOffline ? l("list.noData") : l("list.loading"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}
