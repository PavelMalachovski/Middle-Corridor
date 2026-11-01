import ActivityKit
import MCCore
import SwiftUI
import WidgetKit

/// Live Activity груза: экран блокировки и Dynamic Island. Обновляет приложение (без APNs).
struct ShipmentLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ShipmentActivityAttributes.self) { context in
            LiveStatusLockView(status: context.state, lang: context.attributes.lang)
                .padding()
                .widgetURL(URL(string: "mcstatus://s/\(context.attributes.ref)"))
        } dynamicIsland: { context in
            let status = context.state
            let lang = context.attributes.lang
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label(status.ref, systemImage: LiveStatusStyle.icon(status))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.tone(status.tone))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(LiveStatusStyle.eta(status, lang: lang)).font(.caption)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(status.leg).font(.subheadline).lineLimit(1)
                        HStack {
                            Text(status.status).font(.caption).foregroundStyle(Theme.tone(status.tone))
                            ProgressView(value: status.progress).tint(Theme.tone(status.tone))
                        }
                    }
                }
            } compactLeading: {
                Image(systemName: LiveStatusStyle.icon(status)).foregroundStyle(Theme.tone(status.tone))
            } compactTrailing: {
                Text(LiveStatusStyle.etaShort(status, lang: lang)).font(.caption2)
            } minimal: {
                Image(systemName: LiveStatusStyle.icon(status)).foregroundStyle(Theme.tone(status.tone))
            }
        }
    }
}
