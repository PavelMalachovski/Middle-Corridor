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
    /// Задержка уведомлений после шага (0/5/10 с): успеть заблокировать телефон.
    var notifyDelay: Int {
        didSet { defaults.set(notifyDelay, forKey: Self.delayKey) }
    }
    static let delayKey = "mc.demo.notifyDelay"
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
        notifyDelay = defaults.object(forKey: Self.delayKey) as? Int ?? 5
    }

    /// Жест и кнопки работают только при включённом пульте и сервере с часами демо.
    var isActive: Bool { isEnabled && available }

    /// Статус первого груза из списка — для предпросмотра виджета и Live Activity.
    func previewStatus(lang: Lang) -> LiveStatus? {
        guard let model, let ref = model.store.refs.first, let s = model.store.shipments[ref] else { return nil }
        return LiveStatus.make(s, labels: Labels(lang: lang, nodes: model.store.snapshot?.nodes ?? []))
    }

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
        // заблокировали телефон посреди шага — доделать обновление и Live Activity в фоне
        let background = UIApplication.shared.beginBackgroundTask(withName: "demo-step")
        defer {
            busy = false
            UIApplication.shared.endBackgroundTask(background)
        }
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
