import MCCore
import SwiftUI
import UIKit

/// Цвета статусов — как на сайте (web/src/styles.css): тёмная тема берёт основные
/// оттенки, светлая — тёмные `*-text`, чтобы текст на белом проходил контраст AA.
enum Theme {
    static let accent = Color(light: 0x0B7A55, dark: 0x2FD39A)
    /// Заливка кнопок с белым текстом: мятный акцент тёмной темы с белым не читается (≈ 1,9:1),
    /// поэтому насыщенный зелёный в обеих темах (≈ 5,5:1).
    static let accentStrong = Color(red: 0x0B / 255, green: 0x7A / 255, blue: 0x55 / 255)
    static let ok = Color(light: 0x0F7A33, dark: 0x3DDC5F)
    static let watch = Color(light: 0x8A5A00, dark: 0xFAB219)
    static let warning = Color(light: 0xB24A1C, dark: 0xEC835A)
    static let critical = Color(light: 0xB42318, dark: 0xF07070)

    /// Доставлен — `ok`: успех не должен выглядеть как «ещё не отправлен».
    static func tone(_ tone: StatusTone) -> Color {
        switch tone {
        case .inTransit: accent
        case .waiting: watch
        case .delayed: warning
        case .delivered: ok
        case .planned, .unknown: .secondary
        }
    }

    /// Значок рядом со статусом — смысл передаёт не только цвет.
    static func symbol(_ tone: StatusTone) -> String? {
        switch tone {
        case .delayed: "clock.badge.exclamationmark"
        case .delivered: "checkmark.circle.fill"
        case .planned, .inTransit, .waiting, .unknown: nil
        }
    }

    static func level(_ level: AlertLevel?) -> Color {
        switch level {
        case .critical: critical
        case .warning: warning
        case .watch: watch
        case nil: .secondary
        }
    }
}

extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(
            uiColor: UIColor { traits in
                UIColor(rgb: traits.userInterfaceStyle == .dark ? dark : light)
            })
    }
}

extension UIColor {
    convenience init(rgb: UInt32) {
        self.init(
            red: CGFloat((rgb >> 16) & 0xFF) / 255,
            green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255,
            alpha: 1
        )
    }
}
