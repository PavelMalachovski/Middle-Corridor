import Foundation
import MCCore
import Observation
import UIKit

/// Пульт ведущего: переводит часы мок-бэкенда и обновляет данные приложения.
/// Работает, только если сервер отдаёт `/api/v1/demo/clock` (мок с DEMO_CONTROL=true).
@MainActor
@Observable
final class DemoController {
    static let key = "mc.demo"

    /// Включён ли пульт (долгое нажатие на версию в настройках); переживает перезапуск.
    var isEnabled: Bool {
        didSet { defaults.set(isEnabled, forKey: Self.key) }
    }
    private(set) var state: DemoClockState?
    /// Сервер умеет переводить часы.
    private(set) var available = false
    private(set) var busy = false

    @ObservationIgnored private weak var model: AppModel?
    @ObservationIgnored private let defaults: UserDefaults

    init(model: AppModel, defaults: UserDefaults) {
        self.model = model
        self.defaults = defaults
        isEnabled = defaults.bool(forKey: Self.key)
    }

    /// Жест и кнопки работают только при включённом пульте и сервере с часами демо.
    var isActive: Bool { isEnabled && available }

    func probe() async {
        guard let model else { return }
        do {
            state = try await model.api.demoClock()
            available = true
        } catch {
            state = nil
            available = false
        }
    }

    func perform(_ action: DemoAction) async {
        guard let model, !busy else { return }
        busy = true
        defer { busy = false }
        let feedback = UINotificationFeedbackGenerator()
        do {
            state = try await model.api.demo(action)
            available = true
            await model.store.refresh()
            feedback.notificationOccurred(.success)
        } catch {
            feedback.notificationOccurred(.error)
        }
    }
}
