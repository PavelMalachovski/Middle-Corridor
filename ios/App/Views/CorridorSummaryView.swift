import MCCore
import SwiftUI

/// Пустой список: что происходит в коридоре и кнопка «Добавить груз».
struct CorridorSummaryView: View {
    let store: TrackedShipments
    let onAdd: () -> Void
    @Environment(\.l10n) private var l

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Text(l("empty.title")).font(.title2.bold())
                    Text(l("empty.text")).foregroundStyle(.secondary)
                    Button(action: onAdd) {
                        Label(l("empty.add"), systemImage: "plus")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .accessibilityIdentifier("empty.add")
                }
                .padding(.vertical, 8)
            }

            if store.lastError != nil {
                // риск по погоде — суть продукта: устаревшие данные без пометки показывать нельзя
                Section { OfflineBanner(updatedAt: store.updatedAt) }
            }
            if let snapshot = store.snapshot {
                ports(snapshot)
                week(snapshot)
            } else if store.lastError == nil {
                Section { ProgressView().frame(maxWidth: .infinity) }
            }
        }
    }

    @ViewBuilder
    private func ports(_ snapshot: MapSnapshot) -> some View {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        let risky = snapshot.nodes
            .filter { ($0.alertLevel?.known).map { $0 >= .warning } ?? false }
            .sorted { ($0.alertLevel?.known ?? .watch) > ($1.alertLevel?.known ?? .watch) }
        Section {
            if risky.isEmpty {
                Label(l("corridor.calm"), systemImage: "checkmark.circle")
                    .foregroundStyle(Theme.ok)
            }
            ForEach(risky) { node in
                let level = node.alertLevel?.known
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Image(systemName: "wind")
                        Text(labels.node(node.code) ?? node.name).bold()
                        Spacer()
                        Text(level.map { l("level.\($0.rawValue)") } ?? "")
                            .font(.caption.weight(.semibold))
                    }
                    .foregroundStyle(Theme.level(level))
                    if let speed = node.windSpeed {
                        Text(l("corridor.wind", [
                            "speed": String(Int(speed.rounded())),
                            "gust": String(Int((node.windGust ?? speed).rounded())),
                        ]))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    }
                }
            }
        } header: {
            Text(l("corridor.title")).accessibilityIdentifier("corridor.title")
        }
    }

    @ViewBuilder
    private func week(_ snapshot: MapSnapshot) -> some View {
        if let summary = snapshot.summary {
            Section(l("corridor.week")) {
                LabeledContent(l("corridor.crossings"), value: String(summary.caspianCrossings))
                if let downtime = summary.portDowntimeHours {
                    LabeledContent(l("corridor.downtime"), value: l.hours(downtime))
                }
                if let delay = summary.avgDelayHours {
                    LabeledContent(l("corridor.avgDelay"), value: l.hours(delay))
                }
            }
        }
    }
}

/// Плашка «нет связи»: последние данные остаются на экране.
struct OfflineBanner: View {
    let updatedAt: Date?
    @Environment(\.l10n) private var l

    var body: some View {
        Label {
            Text(updatedAt.map { l("list.offlineSince", ["value": l.relative($0)]) } ?? l("list.offline"))
        } icon: {
            Image(systemName: "wifi.slash")
        }
        .foregroundStyle(Theme.warning)
        .accessibilityIdentifier("offline")
    }
}
