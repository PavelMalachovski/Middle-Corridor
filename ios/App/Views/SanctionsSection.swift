import MCCore
import SwiftUI

/// «Проверка санкций» в карточке груза: статус, совпавшие позиции пакинг-листа (сильные —
/// цветом риска), какие списки и на какую дату. Это подсказка для ручной проверки, не вердикт.
struct SanctionsSection: View {
    let check: SanctionsCheck
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        Section(l("card.sanctions")) {
            VStack(alignment: .leading, spacing: 8) {
                Label(labels.sanctionsStatus(check), systemImage: icon)
                    .font(.headline)
                    .foregroundStyle(color)
                ForEach(Array(check.matches.enumerated()), id: \.offset) { _, match in
                    Text(labels.sanctionsMatch(match, lists: check.lists))
                        .font(.subheadline)
                        .foregroundStyle(match.strong ? Theme.critical : Color.secondary)
                }
                ForEach(check.lists, id: \.code) { info in
                    Text(l("card.sanctions.asOf", ["list": labels.listName(info), "date": Self.date(info.asOf)]))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(l("card.sanctions.disclaimer"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("card.sanctions")
        }
    }

    private var icon: String {
        switch check.status.known {
        case .flagged: "exclamationmark.shield.fill"
        case .missing: "doc.text.magnifyingglass"
        case .review: "magnifyingglass"
        case .clear: "checkmark.shield"
        case .pending, nil: "clock"
        }
    }

    private var color: Color {
        switch check.status.known {
        case .flagged, .missing: Theme.critical
        case .review: Theme.warning
        case .clear: Theme.ok
        case .pending, nil: .secondary
        }
    }

    /// Возможна санкционка, нет листа после границы или «проверить вручную» — блок наверху карточки.
    static func needsAttention(_ check: SanctionsCheck) -> Bool {
        switch check.status.known {
        case .flagged, .missing, .review: true
        case .clear, .pending, nil: false
        }
    }

    /// «2026-07-24» → «24.07.2026».
    static func date(_ iso: String) -> String {
        iso.split(separator: "-").reversed().joined(separator: ".")
    }
}
