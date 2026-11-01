import Foundation

/// Тон статуса груза — цвет «пилюли», как на сайте (`.pill--*` в web/src/styles.css).
public enum StatusTone: String, Codable, Sendable, Equatable {
    case planned, inTransit, waiting, delayed, delivered, unknown
}

extension Shipment {
    /// Задержка — как на сайте: от часа и только у недоставленных.
    public var isDelayed: Bool { delayHours >= 1 && state.known != .delivered }

    public var tone: StatusTone {
        guard let state = state.known else { return .unknown }
        if state == .delivered { return .delivered }
        if isDelayed { return .delayed }
        switch state {
        case .planned: return .planned
        case .inTransit: return .inTransit
        case .waiting: return .waiting
        case .delivered: return .delivered
        }
    }
}

/// «Сейчас» в карточке: что известно о положении груза и насколько это факт.
public struct PositionText: Sendable, Equatable {
    public var title: String
    public var detail: String
    /// false — оценка по расписанию: показывать как предположение, не как факт.
    public var confirmed: Bool
}

/// Подписи из кодов бэкенда — порт web/src/i18n/labels.ts и positionText из ShipmentCard.tsx.
///
/// Бэкенд отдаёт русскую строку и рядом код; по-английски подпись собирается из кода,
/// а неизвестный код оставляет русскую строку бэкенда.
public struct Labels: Sendable {
    public let lang: Lang
    private let nodes: [String: NodeStatus]

    private static let noteCodes: Set<String> = ["loaded_on_ferry", "loaded_on_vessel", "gauge_change_done"]
    private static let holdCodes: Set<String> = [
        "weather_ban", "customs_wait", "ferry_loading_wait", "ferry_return_wait",
    ]

    public init(lang: Lang, nodes: [NodeStatus]) {
        self.lang = lang
        self.nodes = Dictionary(nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
    }

    /// Имя узла на языке интерфейса; неизвестный код — nil.
    public func node(_ code: String?) -> String? {
        guard let code, let node = nodes[code] else { return nil }
        return lang == .en ? (node.nameEn ?? node.name) : node.name
    }

    public func state(_ s: Shipment) -> String {
        s.state.known == nil ? s.state.raw : t("state.\(s.state.raw)")
    }

    public func cargo(_ s: Shipment) -> String {
        lang == .en ? (s.cargoEn ?? s.cargo) : s.cargo
    }

    public func route(_ s: Shipment) -> String {
        "\(node(s.originCode) ?? s.origin) → \(node(s.destinationCode) ?? s.destination)"
    }

    public func checkpoint(_ c: Checkpoint) -> String {
        node(c.code) ?? c.name
    }

    public func event(_ s: Shipment) -> String {
        guard let kind = s.lastEventKind else {
            return lang == .ru ? s.lastEvent : t("event.none")
        }
        if lang == .ru && s.lastEventNoteCode == nil { return s.lastEvent }  // бэкенд уже собрал строку
        guard kind.known != nil else { return s.lastEvent }
        let base = t("event.\(kind.raw)", ["node": nameOrCode(s.lastEventNode)])
        if let code = s.lastEventNoteCode, Self.noteCodes.contains(code) {
            return "\(base) — \(t("note.\(code)", ["vessel": s.lastEventNoteVessel ?? ""]))"
        }
        return lang == .ru ? s.lastEvent : base
    }

    public func hold(_ s: Shipment) -> String? {
        if s.holdReason == nil && s.holdCode == nil { return nil }
        if let code = s.holdCode, Self.holdCodes.contains(code) {
            return t("hold.\(code)", ["node": nameOrCode(s.holdNode), "vessel": s.holdVessel ?? ""])
        }
        return s.holdReason
    }

    public func position(_ s: Shipment) -> PositionText {
        let p = s.position
        if s.state.known == .delivered {
            return PositionText(
                title: t("card.delivered", ["node": node(s.destinationCode) ?? s.destination]),
                detail: t("card.routeDone"),
                confirmed: true
            )
        }
        switch p.source.known {
        case .event:
            let detail = p.toCode.map { t("card.confirmedNext", ["node": nameOrCode($0)]) } ?? t("card.confirmed")
            return PositionText(
                title: t("card.atNode", ["node": nameOrCode(p.fromCode)]), detail: detail, confirmed: true)
        case .ais:
            return PositionText(
                title: t("card.onFerry", ["vessel": p.onVessel ?? ""]),
                detail: "\(nameOrCode(p.fromCode)) → \(nameOrCode(p.toCode))",
                confirmed: p.confirmed
            )
        case .projection, nil:  // неизвестный источник — тоже не факт
            let vehicle =
                p.onVessel.map { t("card.onVessel", ["vessel": $0]) }
                ?? (p.mode?.known == .sea ? t("card.atSea") : t("card.byRail"))
            return PositionText(
                title: t("card.legProgress", [
                    "from": nameOrCode(p.fromCode),
                    "to": nameOrCode(p.toCode),
                    "pct": String(Int((p.legProgress * 100).rounded())),
                ]),
                detail: t("card.estimate", ["vehicle": vehicle]),
                confirmed: false
            )
        }
    }

    /// Текст по ключу на языке подписей (уведомления, Live Activity).
    public func text(_ key: String, _ params: [String: String] = [:]) -> String { t(key, params) }

    /// Часы как на сайте: «меньше часа», «18 ч», «2 д 18 ч».
    public func hours(_ value: Double) -> String {
        if value < 1 { return t("unit.lessThanHour") }
        if value < 48 { return t("unit.hours", ["value": String(Int(value.rounded()))]) }
        let days = Int(value / 24)
        let rest = Int((value - Double(days) * 24).rounded())
        return t("unit.days", ["days": String(days), "hours": String(rest)])
    }

    /// «7 нояб., 23:00» / «Nov 7, 11:00 PM».
    public func dateTime(_ date: Date) -> String {
        date.formatted(.dateTime.day().month(.abbreviated).hour().minute().locale(Locale(identifier: lang.rawValue)))
    }

    /// Прогноз очереди словами: ожидаемо («2–3 дня», «≈ 12 ч») и в плохом сценарии («до 5 дней»).
    public func queue(_ q: QueueForecast) -> (main: String, worst: String) {
        let main: String
        if q.p50Hours < 24 {
            main = "≈ \(Int(q.p50Hours.rounded())) \(lang == .en ? "h" : "ч")"
        } else {
            let lo = Int((q.p50Hours / 24).rounded(.down))
            let hi = Int((q.p50Hours / 24).rounded(.up))
            let range = lo == hi ? "\(hi)" : "\(lo)–\(hi)"
            main = "\(range) \(lang == .en ? (hi == 1 ? "day" : "days") : Self.daysRu(hi))"
        }
        let worst: String
        if q.p90Hours < 24 {
            let h = Int(q.p90Hours.rounded())
            worst = lang == .en ? "up to \(h) h" : "до \(h) ч"
        } else {
            let n = Int((q.p90Hours / 24).rounded(.up))
            let oneLike = n % 10 == 1 && n % 100 != 11
            worst = lang == .en ? "up to \(n) \(n == 1 ? "day" : "days")" : "до \(n) \(oneLike ? "дня" : "дней")"
        }
        return (main, worst)
    }

    /// 1 день, 2–4 дня, 5+ дней (11–14 — дней).
    private static func daysRu(_ n: Int) -> String {
        let (mod10, mod100) = (n % 10, n % 100)
        if mod10 == 1 && mod100 != 11 { return "день" }
        if (2...4).contains(mod10) && !(12...14).contains(mod100) { return "дня" }
        return "дней"
    }

    private func nameOrCode(_ code: String?) -> String {
        node(code) ?? code ?? ""
    }

    private func t(_ key: String, _ params: [String: String] = [:]) -> String {
        Strings.t(lang, key, params)
    }
}
