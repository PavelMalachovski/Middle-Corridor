import ActivityKit
import MCCore

/// Live Activity грузов: одна на номер, запуск — кнопкой в карточке, обновление — при каждом
/// обновлении данных, «доставлен» — финальное состояние и закрытие через минуту.
/// Без привязки к MainActor: `Activity` не Sendable, и работать с ней надо там же, где её нашли.
enum LiveActivities {
    static var enabled: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }

    private static func activity(_ ref: String) -> Activity<ShipmentActivityAttributes>? {
        Activity<ShipmentActivityAttributes>.activities.first { $0.attributes.ref == ref }
    }

    static func isActive(_ ref: String) -> Bool { activity(ref) != nil }

    static func start(_ s: Shipment, labels: Labels) throws {
        guard !isActive(s.ref) else { return }
        _ = try Activity.request(
            attributes: ShipmentActivityAttributes(ref: s.ref, lang: labels.lang),
            content: ActivityContent(state: LiveStatus.make(s, labels: labels), staleDate: nil),
            pushType: nil)
    }

    static func stop(_ ref: String) async {
        await activity(ref)?.end(nil, dismissalPolicy: .immediate)
    }

    static func update(_ shipments: [String: Shipment], labels: Labels) async {
        for activity in Activity<ShipmentActivityAttributes>.activities {
            guard let s = shipments[activity.attributes.ref] else { continue }
            let content = ActivityContent(state: LiveStatus.make(s, labels: labels), staleDate: nil)
            if content.state.delivered {
                await activity.end(content, dismissalPolicy: .after(.now.addingTimeInterval(60)))
            } else {
                await activity.update(content)
            }
        }
    }
}
