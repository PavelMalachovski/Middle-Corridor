import MCCore
import SwiftUI

/// Статус груза «пилюлей»: тонированная заливка цветом тона, задержка — «+N ч» со значком.
struct StatusPill: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let tone = shipment.tone
        let neutral = tone == .planned || tone == .unknown
        let color = Theme.tone(tone)
        HStack(spacing: 3) {
            if let symbol = Theme.symbol(tone) {
                Image(systemName: symbol).imageScale(.small)
            }
            Text(text).monospacedDigit()
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(neutral ? Color.primary : color)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        // заливка 10% вместо обводки 50% (та давала ≈2,2:1 к фону); при 14% текст на белом падал ниже 4,5:1
        .background(neutral ? Color.primary.opacity(0.08) : color.opacity(0.10), in: Capsule())
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("pill.\(shipment.ref)")
    }

    private var text: String {
        let state = labels.state(shipment)
        return shipment.isDelayed ? "\(state) · +\(l.hours(shipment.delayHours))" : state
    }
}
