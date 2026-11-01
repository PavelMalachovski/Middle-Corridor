import ActivityKit
import MCCore

/// Live Activity груза: номер — неизменная часть, `LiveStatus` — состояние, которое обновляет приложение.
/// Язык — в атрибутах: расширение не видит настроек приложения (без App Group на iPhone).
struct ShipmentActivityAttributes: ActivityAttributes {
    typealias ContentState = LiveStatus
    let ref: String
    let lang: Lang
}
