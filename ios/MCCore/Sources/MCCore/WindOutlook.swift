import Foundation

/// Вывод по прогнозу ветра одной строкой под графиком: худший уровень впереди и до каких пор.
public struct WindOutlook: Equatable, Sendable {
    /// Максимальная скорость ветра впереди (м/с).
    public let peak: Double
    /// Максимальные порывы впереди (м/с): уровень часто держат именно они, а не средний ветер.
    public let peakGust: Double
    /// Худший уровень предиктора впереди; nil — спокойно.
    public let level: AlertLevel?
    /// Последний час с этим уровнем; nil — уровень держится до конца прогноза.
    public let until: Date?
    /// Часов впереди с худшим уровнем и всего часов впереди: «весь прогноз» — только если они равны,
    /// иначе провал посередине выдавался бы за сплошной шторм.
    public let hoursAtLevel: Int
    public let totalHours: Int

    /// Худший уровень держится каждый час прогноза, без провалов.
    public var isWhole: Bool { level != nil && hoursAtLevel == totalHours }

    public init(hours: [WindHour], now: Date) {
        let ahead = hours.filter { $0.ts >= now }.sorted { $0.ts < $1.ts }
        let window = ahead.isEmpty ? hours : ahead
        peak = window.map(\.speed).max() ?? 0
        peakGust = window.map(\.gust).max() ?? 0
        totalHours = window.count
        let worst = window.compactMap { $0.level?.known }.max()
        level = worst
        hoursAtLevel = worst.map { level in window.filter { $0.level?.known == level }.count } ?? 0
        guard let worst, let last = window.last else {
            until = nil
            return
        }
        let lastAtLevel = window.last(where: { $0.level?.known == worst })?.ts
        until = lastAtLevel == last.ts ? nil : lastAtLevel
    }
}
