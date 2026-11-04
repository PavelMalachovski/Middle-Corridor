import Foundation

/// Кадр заставки «Переправа»: доли 0…1, рисует `SplashView` в приложении.
public struct SplashFrame: Equatable, Sendable {
    /// Рельсы от краёв экрана к портам.
    public var rails: Double
    /// Паром на переправе: 0 — Актау, 1 — Алят.
    public var ferry: Double
    public var ferryOpacity: Double
    /// Подпись «Middle Corridor · Aktau → Alat».
    public var wordmark: Double
    /// Прозрачность всей заставки (0 — под ней уже приложение).
    public var opacity: Double

    public init(rails: Double, ferry: Double, ferryOpacity: Double, wordmark: Double, opacity: Double) {
        self.rails = rails
        self.ferry = ferry
        self.ferryOpacity = ferryOpacity
        self.wordmark = wordmark
        self.opacity = opacity
    }
}

/// Шкала заставки (секунды от первого кадра). Кадр 0 совпадает со статичным экраном запуска:
/// море, точки переправы и порты — без рельсов, парома и подписи.
public enum SplashTimeline {
    public static let duration = 1.75
    /// Тап по заставке — быстрое растворение.
    public static let skipFade = 0.2

    private static let rails = (start: 0.0, end: 0.45)
    private static let ferry = (start: 0.35, end: 1.15)
    private static let ferryAppear = (start: 0.35, end: 0.45)
    private static let wordmark = (start: 0.8, end: 1.15)
    private static let fadeOut = (start: 1.45, end: duration)

    /// `skippedAt` — когда тапнули: затухание за `skipFade` от текущего кадра, без скачка яркости.
    public static func frame(at t: Double, skippedAt: Double? = nil) -> SplashFrame {
        let t = clamp(t, 0, duration)
        var opacity = 1 - phase(t, fadeOut)
        if let skippedAt {
            opacity = min(opacity, 1 - clamp((t - skippedAt) / skipFade, 0, 1))
        }
        let railsLinear = phase(t, rails)
        return SplashFrame(
            rails: 1 - (1 - railsLinear) * (1 - railsLinear),  // ease-out: рельсы «прибывают» и тормозят
            ferry: smoothstep(phase(t, ferry)),
            ferryOpacity: phase(t, ferryAppear),
            wordmark: phase(t, wordmark),
            opacity: opacity
        )
    }

    public static func isFinished(at t: Double, skippedAt: Double?) -> Bool {
        let tolerance = 1e-9  // 0,4 + 0,2 в double больше 0,6
        if t >= duration - tolerance { return true }
        if let skippedAt, t >= skippedAt + skipFade - tolerance { return true }
        return false
    }

    private static func phase(_ t: Double, _ range: (start: Double, end: Double)) -> Double {
        clamp((t - range.start) / (range.end - range.start), 0, 1)
    }

    private static func smoothstep(_ x: Double) -> Double { x * x * (3 - 2 * x) }

    private static func clamp(_ x: Double, _ low: Double, _ high: Double) -> Double {
        x.isNaN ? low : min(max(x, low), high)
    }
}
