import MCCore
import SwiftUI

/// Порт: уровень риска, ветер сейчас и прогноз на 48 часов.
struct PortDetailView: View {
    let code: String
    let store: TrackedShipments
    @Environment(\.l10n) private var l

    var body: some View {
        let snapshot = store.snapshot
        let node = snapshot?.nodes.first { $0.code == code }
        let name = node.flatMap { Labels(lang: l.lang, nodes: snapshot?.nodes ?? []).node($0.code) } ?? code
        List {
            if let node, let snapshot {
                Section(l("card.now")) {
                    PortRow(node: node, name: name)
                }
                if let forecast = node.forecast, !forecast.isEmpty {
                    Section(l("port.forecast")) {
                        WindChart(hours: forecast, thresholds: snapshot.thresholds, now: snapshot.generatedAt)
                            .padding(.vertical, 8)
                    }
                }
            } else {
                ContentUnavailableView(l("list.noData"), systemImage: "wind")
            }
        }
        .navigationTitle(name)
        .navigationBarTitleDisplayMode(.inline)
    }
}
