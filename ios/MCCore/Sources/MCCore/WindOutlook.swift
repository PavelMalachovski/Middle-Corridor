import Foundation

/// Вывод по прогнозу ветра одной строкой под графиком: худший уровень впереди и до каких пор.
public struct WindOutlook: Equatable, Sendable {
    /// Максимальная скорость ветра впереди (м/с).
    public let peak: Double
    /// Худший уровень предиктора впереди; nil — спокойно.
    public let level: AlertLevel?
    /// Последний час с этим уровнем; nil — уровень держится до конца прогноза.
    public let until: Date?

    public init(hours: [WindHour], now: Date) {
        let ahead = hours.filter { $0.ts >= now }.sorted { $0.ts < $1.ts }
        let window = ahead.isEmpty ? hours : ahead
        peak = window.map(\.speed).max() ?? 0
        let worst = window.compactMap { $0.level?.known }.max()
        level = worst
        guard let worst, let last = window.last else {
            until = nil
            return
        }
        let lastAtLevel = window.last(where: { $0.level?.known == worst })?.ts
        until = lastAtLevel == last.ts ? nil : lastAtLevel
    }
}
