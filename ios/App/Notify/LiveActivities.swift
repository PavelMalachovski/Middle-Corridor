import ActivityKit
import MCCore

/// Live Activity грузов: одна на номер, запуск — кнопкой в карточке, обновление — при каждом
/// обновлении данных, «доставлен» — финальное состояние и закрытие через минуту.
/// Без привязки к MainActor: `Activity` не Sendable, и работать с ней надо там же, где её нашли.
enum LiveActivities {
    static var enabled: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }

    /// Живые активности: завершённые остаются в списке до закрытия — их не трогаем.
    private static var live: [Activity<ShipmentActivityAttributes>] {
        Activity<ShipmentActivityAttributes>.activities.filter {
            $0.activityState == .active || $0.activityState == .stale
        }
    }

    private static func activity(_ ref: String) -> Activity<ShipmentActivityAttributes>? {
        live.first { $0.attributes.ref == ref }
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

    /// Все активности — «Сброс истории» в пульте: после репетиции экран блокировки чистый.
    static func stopAll() async {
        for activity in live { await activity.end(nil, dismissalPolicy: .immediate) }
    }

    static func update(_ shipments: [String: Shipment], labels: Labels) async {
        for activity in live {
            guard let s = shipments[activity.attributes.ref] else {
                // груза больше нет в списке — активность не должна висеть
                await activity.end(nil, dismissalPolicy: .immediate)
                continue
            }
            let content = ActivityContent(state: LiveStatus.make(s, labels: labels), staleDate: nil)
            if content.state.delivered {
                await activity.end(content, dismissalPolicy: .after(.now.addingTimeInterval(60)))
            } else {
                await activity.update(content)
            }
        }
    }
}
