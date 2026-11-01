import MCCore
import SwiftUI

/// Прогноз выхода из очереди: ожидаемо, плохой сценарий, место и темп отгрузки.
struct QueueSection: View {
    let queue: QueueForecast
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let text = labels.queue(queue)
        Section(l("card.queue", ["port": labels.node(queue.portCode) ?? queue.portCode])) {
            VStack(alignment: .leading, spacing: 4) {
                Text(l("queue.main", ["value": text.main])).font(.headline)
                Text(l("queue.worst", ["value": text.worst])).foregroundStyle(.secondary)
                Text(l("queue.place", [
                    "position": String(queue.position),
                    "perDay": String(Int(queue.perDay.rounded())),
                ]))
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("card.queue")
        }
    }
}
