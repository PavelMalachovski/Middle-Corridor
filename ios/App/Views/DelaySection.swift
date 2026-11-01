import MCCore
import SwiftUI

/// «Почему задержка»: причины с часами, сумма — та же «Задержка +N ч», что выше.
struct DelaySection: View {
    let parts: [DelayPart]
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        Section(l("card.whyDelay")) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                    HStack(alignment: .firstTextBaseline) {
                        Text(labels.delayPart(part))
                        Spacer()
                        Text("+\(l.hours(part.hours))")
                            .foregroundStyle(part.code == "schedule" ? Color.secondary : Theme.warning)
                            .monospacedDigit()
                    }
                }
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("card.delayBreakdown")
        }
    }
}

/// Строка «Прибытие»: вилка «6–9 нояб.» и под ней «обычно …, в плохом случае …».
struct EtaRow: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let range = shipment.eta.map { labels.etaRange($0, shipment.etaLatest) } ?? "—"
        VStack(alignment: .leading, spacing: 2) {
            LabeledContent(l("card.eta"), value: range)
            if let eta = shipment.eta, let latest = shipment.etaLatest, latest.timeIntervalSince(eta) >= 12 * 3600 {
                Text(l("card.etaRange", ["usual": l.dateTime(eta), "worst": l.dateTime(latest)]))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("card.eta")
    }
}
