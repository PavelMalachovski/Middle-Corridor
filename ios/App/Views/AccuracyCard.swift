import MCCore
import SwiftUI

/// «Точность прогноза» по коридору: сколько остановок предупредили и за сколько часов.
struct AccuracyCard: View {
    let report: AccuracyReport
    @Environment(\.l10n) private var l

    var body: some View {
        let text = Labels(lang: l.lang, nodes: []).accuracy(AccuracySummary.make(report))
        Section(l("accuracy.title", ["days": String(report.days)])) {
            VStack(alignment: .leading, spacing: 4) {
                Label(text.main, systemImage: "checkmark.seal.fill")
                    .font(.headline)
                    .foregroundStyle(Theme.ok)
                Text(text.detail).font(.subheadline).foregroundStyle(.secondary)
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("accuracy.summary")
            if report.demo == true {
                Text(l("accuracy.demo"))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("accuracy.demo")
            }
        }
    }
}

/// Точность прогноза по одному порту — в экране порта.
struct PortAccuracySection: View {
    let port: PortAccuracy
    let days: Int
    let demo: Bool
    @Environment(\.l10n) private var l

    var body: some View {
        let summary = AccuracySummary(
            closures: port.closures, hits: port.hits, alerts: port.alerts, falseAlarms: port.falseAlarms,
            medianLeadH: port.medianLeadH)
        let text = Labels(lang: l.lang, nodes: []).accuracy(summary)
        Section(l("accuracy.title", ["days": String(days)])) {
            VStack(alignment: .leading, spacing: 4) {
                Text(port.closures == 0 ? l("accuracy.none") : text.main).font(.headline)
                if port.closures > 0 { Text(text.detail).font(.subheadline).foregroundStyle(.secondary) }
                if demo { Text(l("accuracy.demo")).font(.caption2).foregroundStyle(.secondary) }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("port.accuracy")
        }
    }
}
