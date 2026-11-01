import Foundation
import MCCore
import UserNotifications

/// Локальные уведомления: без APNs и платного аккаунта Apple. Баннер — и на переднем плане.
@MainActor
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    private let center = UNUserNotificationCenter.current()
    /// Нажали на уведомление — открыть груз (задаёт AppModel).
    var onOpen: ((String) -> Void)?

    override init() {
        super.init()
        center.delegate = self
    }

    /// Спрашиваем после первого добавленного груза, не на старте: на демо системный диалог на шаге 1 мешает.
    func requestAuthorizationIfNeeded() async {
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .notDetermined else { return }
        _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// `delay` > 0 — ведущий успевает заблокировать телефон, и уведомление приходит на экран блокировки.
    func deliver(_ notices: [AppNotice], after delay: TimeInterval) {
        for notice in notices {
            let content = UNMutableNotificationContent()
            content.title = notice.title
            content.body = notice.body
            content.sound = .default
            content.threadIdentifier = notice.ref
            content.userInfo = ["ref": notice.ref, "kind": notice.kind.rawValue]
            let trigger = delay > 0 ? UNTimeIntervalNotificationTrigger(timeInterval: delay, repeats: false) : nil
            center.add(UNNotificationRequest(identifier: notice.id, content: content, trigger: trigger))
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .list]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse
    ) async {
        guard let ref = response.notification.request.content.userInfo["ref"] as? String else { return }
        await open(ref)
    }

    private func open(_ ref: String) { onOpen?(ref) }

    /// «Сброс истории»: старые баннеры о будущем, которое отменили, не нужны.
    func clearDelivered() {
        center.removeAllDeliveredNotifications()
        center.removeAllPendingNotificationRequests()
    }
}

/// Какие уведомления включены (настройки, `mc.notify.*`; по умолчанию все).
enum NotifyPrefs {
    static func key(_ kind: NoticeKind) -> String { "mc.notify.\(kind.rawValue)" }

    static func load(_ defaults: UserDefaults = .standard) -> NotifySettings {
        func on(_ kind: NoticeKind) -> Bool { defaults.object(forKey: key(kind)) as? Bool ?? true }
        return NotifySettings(storm: on(.storm), event: on(.event), delay: on(.delay), queue: on(.queue))
    }
}
