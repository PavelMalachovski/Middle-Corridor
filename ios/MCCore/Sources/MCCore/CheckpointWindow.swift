import Foundation

/// Какие точки маршрута показать в карточке сразу, а какие свернуть.
///
/// Видны последняя пройденная точка, текущая и три следующие; остальное прячется
/// в строки «Пройдено N точек» и «Ещё N точек». Одна спрятанная точка не стоит отдельной
/// строки — её показываем как есть.
public struct CheckpointWindow: Equatable, Sendable {
    /// Индексы видимых точек.
    public let visible: ClosedRange<Int>
    /// Сколько точек свёрнуто до и после видимых.
    public var hiddenBefore: Int { visible.lowerBound }
    public let hiddenAfter: Int

    public static let ahead = 3

    public init(states: [CheckpointState?]) {
        let count = states.count
        guard count > 0 else {
            visible = 0...0
            hiddenAfter = 0
            return
        }
        let pivot = states.firstIndex(of: .current) ?? states.lastIndex(of: .done) ?? 0
        var lo = max(0, pivot - 1)
        var hi = min(count - 1, pivot + Self.ahead)
        if lo == 1 { lo = 0 }
        if hi == count - 2 { hi = count - 1 }
        visible = lo...hi
        hiddenAfter = count - 1 - hi
    }

    public init(_ checkpoints: [Checkpoint]) {
        self.init(states: checkpoints.map { $0.state.known })
    }
}
