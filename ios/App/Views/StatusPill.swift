import MCCore
import SwiftUI

/// Статус груза «пилюлей», как на сайте: цвет по тону, задержка — «+N ч».
struct StatusPill: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let color = Theme.tone(shipment.tone)
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .overlay(Capsule().strokeBorder(color.opacity(0.5)))
            .accessibilityIdentifier("pill.\(shipment.ref)")
    }

    private var text: String {
        let state = labels.state(shipment)
        return shipment.isDelayed ? "\(state) · +\(l.hours(shipment.delayHours))" : state
    }
}
