import MCCore
import SwiftUI

/// Погода в порту, где груз стоит (или в ближайшем впереди): ветер сейчас и прогноз.
struct PortWeatherSection: View {
    let port: NodeStatus
    let snapshot: MapSnapshot
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let name = labels.node(port.code) ?? port.name
        Section(l("card.weather", ["port": name])) {
            PortRow(node: port, name: name)
                .accessibilityIdentifier("card.weather")
            if let forecast = port.forecast, !forecast.isEmpty {
                WindChart(hours: forecast, thresholds: snapshot.thresholds, now: snapshot.generatedAt)
                    .padding(.vertical, 8)
            }
        }
    }
}
