import Foundation
import MCCore

/// Ссылки, которыми делятся грузом.
///
/// Наружу уходит https-ссылка на веб-карту (`?s=<номер>`): её откроет любой мессенджер и любой
/// получатель, а с Universal Links — и приложение. `mcstatus://` мессенджеры не делают ссылкой,
/// поэтому он остаётся только внутренним (виджет, Live Activity). Адрес сайта — ключ сборки
/// `MC_SHARE_BASE_URL` (project.yml → Info.plist `MCShareBaseURL`).
enum AppLinks {
    static let baseURLKey = "MCShareBaseURL"

    static var shareBase: URL? {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: baseURLKey) as? String,
            let url = URL(string: raw.trimmingCharacters(in: .whitespaces)),
            let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http"
        else { return nil }
        return url
    }

    /// https-ссылка на груз; без настроенного сайта — `mcstatus://s/<номер>`.
    static func share(_ ref: String) -> URL {
        if let base = shareBase { return ShipmentRef.shareURL(ref: ref, base: base) }
        return internalURL(ref)
    }

    /// Ссылка внутри устройства: виджет, Live Activity, уведомления.
    static func internalURL(_ ref: String) -> URL {
        URL(string: "mcstatus://s/\(ref)") ?? URL(fileURLWithPath: "/")
    }

    /// «MC-26-0398 · Стоянка · +18 ч · прибытие 6 нояб., 17:08».
    static func message(_ s: Shipment, labels: Labels, l: L10n) -> String {
        var status = labels.state(s)
        if s.isDelayed { status += " · +\(l.hours(s.delayHours))" }
        guard let eta = s.eta, s.state.known != .delivered else {
            return l("share.messageNoEta", ["ref": s.ref, "status": status])
        }
        return l("share.message", ["ref": s.ref, "status": status, "eta": l.dateTime(eta)])
    }
}
