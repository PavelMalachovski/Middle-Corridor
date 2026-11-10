import MCCore
import Observation
import UIKit
import os

/// Push о событиях грузов аккаунта (APNs). Нужен `aps-environment` — его даёт только платный
/// Apple Developer; узнать его из приложения нельзя, поэтому сборка говорит сама: Info.plist
/// `MCPushEnabled` (`$(MC_PUSH_ENABLED)`, по умолчанию NO). Выключено — регистрации нет, а
/// о грузах аккаунта говорят локальные уведомления (`NotificationRules.diff`).
@MainActor
@Observable
final class PushRegistration {
    /// Сервер принял токен устройства — о событиях грузов аккаунта приходит push,
    /// локальное «событие» по ним молчит (иначе дубль).
    private(set) var isRegistered = false

    @ObservationIgnored private weak var account: AccountModel?
    private static let log = Logger(subsystem: "com.malakhouski.mcstatus", category: "push")

    static var isEnabled: Bool {
        switch Bundle.main.object(forInfoDictionaryKey: "MCPushEnabled") {
        case let flag as Bool: flag
        case let text as String: ["yes", "true", "1"].contains(text.lowercased())
        default: false
        }
    }

    static var environment: String {
        #if DEBUG
            "sandbox"
        #else
            "production"
        #endif
    }

    init() {
        AppDelegate.onToken = { [weak self] token in
            Task { await self?.didReceive(token: token) }
        }
    }

    /// После входа (и на каждом старте с сохранённым входом — токен мог смениться): разрешение
    /// на уведомления, затем — токен APNs, если push есть в сборке.
    func start(account: AccountModel, notifier: Notifier) async {
        self.account = account
        await notifier.requestAuthorizationIfNeeded()
        guard Self.isEnabled, await notifier.isAuthorized() else { return }
        UIApplication.shared.registerForRemoteNotifications()
    }

    /// Вышли: до нового входа (и новой регистрации) грузов аккаунта нет — и push по ним не ждём.
    func reset() {
        isRegistered = false
    }

    private func didReceive(token: Data) async {
        guard let account, account.isSignedIn else { return }
        do {
            try await account.registerDevice(token: PushToken.hex(token), environment: Self.environment)
            isRegistered = true
        } catch {
            // токен в лог не пишем — только что не вышло
            Self.log.error("device registration failed: \(String(describing: APIError.from(error)), privacy: .public)")
        }
    }
}

/// Токен APNs приходит только в делегат приложения.
@MainActor
final class AppDelegate: NSObject, UIApplicationDelegate {
    static var onToken: ((Data) -> Void)?

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        Self.onToken?(token)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: any Error) {
        Logger(subsystem: "com.malakhouski.mcstatus", category: "push")
            .error("APNs registration failed: \(error.localizedDescription, privacy: .public)")
    }
}
