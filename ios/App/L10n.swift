import Foundation
import MCCore
import SwiftUI

/// Выбор языка в настройках: как в системе или явно.
enum LangChoice: String, CaseIterable, Identifiable {
    case system, ru, en
    var id: String { rawValue }

    static let key = "mc.lang"

    /// Язык интерфейса: явный выбор или первый из системных (`ru*` → ru, иначе en).
    func resolved(preferred: [String] = Locale.preferredLanguages) -> Lang {
        switch self {
        case .ru: .ru
        case .en: .en
        case .system: preferred.first?.lowercased().hasPrefix("ru") == true ? .ru : .en
        }
    }
}

/// Тексты интерфейса из Localizable.xcstrings на выбранном языке (не системном):
/// язык переключается в приложении, поэтому таблица берётся из нужного .lproj.
struct L10n: Sendable {
    let lang: Lang

    func callAsFunction(_ key: String, _ params: [String: String] = [:]) -> String {
        var text = bundle.localizedString(forKey: key, value: nil, table: "Localizable")
        for (name, value) in params {
            text = text.replacingOccurrences(of: "{\(name)}", with: value)
        }
        return text
    }

    var locale: Locale { Locale(identifier: lang.rawValue) }

    /// Часы как на сайте (web/src/format.ts fmtHours).
    func hours(_ value: Double) -> String {
        if value < 1 { return self("unit.lessThanHour") }
        if value < 48 { return self("unit.hours", ["value": String(Int(value.rounded()))]) }
        let days = Int(value / 24)
        let rest = Int((value - Double(days) * 24).rounded())
        return self("unit.days", ["days": String(days), "hours": String(rest)])
    }

    func dateTime(_ date: Date) -> String {
        date.formatted(.dateTime.day().month(.abbreviated).hour().minute().locale(locale))
    }

    func relative(_ date: Date) -> String {
        date.formatted(.relative(presentation: .named).locale(locale))
    }

    private var bundle: Bundle {
        Bundle.main.path(forResource: lang.rawValue, ofType: "lproj").flatMap(Bundle.init(path:)) ?? .main
    }
}

private struct L10nKey: EnvironmentKey {
    static let defaultValue = L10n(lang: .ru)
}

extension EnvironmentValues {
    var l10n: L10n {
        get { self[L10nKey.self] }
        set { self[L10nKey.self] = newValue }
    }
}
