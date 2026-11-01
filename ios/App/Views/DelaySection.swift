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
