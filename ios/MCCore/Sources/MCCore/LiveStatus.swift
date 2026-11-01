import Foundation

/// Что груз делает сейчас — для значка в Dynamic Island.
public enum LivePhase: String, Codable, Sendable {
    case stop, sea, rail, done
}

/// Статус груза для Live Activity и виджета: короткие готовые строки на языке интерфейса.
/// Это `ContentState` активности — поэтому Codable и без ссылок на модели API.
public struct LiveStatus: Codable, Hashable, Sendable {
    public var ref: String
    /// «Актау» (стоит) · «Курык → паром «Barda» → Баку (Алят)» (в пути) · «Констанца» (доставлен).
    public var leg: String
    /// «Стоянка · +18 ч», «В пути».
    public var status: String
    public var eta: Date?
    public var delayHours: Double
    public var progress: Double
    public var tone: StatusTone
    public var phase: LivePhase
    public var delivered: Bool

    public init(
        ref: String, leg: String, status: String, eta: Date?, delayHours: Double, progress: Double,
        tone: StatusTone, phase: LivePhase, delivered: Bool
    ) {
        self.ref = ref
        self.leg = leg
        self.status = status
        self.eta = eta
        self.delayHours = delayHours
        self.progress = progress
        self.tone = tone
        self.phase = phase
        self.delivered = delivered
    }

    public static func make(_ s: Shipment, labels: Labels) -> LiveStatus {
        let p = s.position
        let delivered = s.state.known == .delivered
        let name = { (code: String?) in labels.node(code) ?? code ?? "—" }
        let leg: String
        let phase: LivePhase
        if delivered {
            leg = name(s.destinationCode)
            phase = .done
        } else if p.mode == nil {
            leg = name(p.fromCode)
            phase = .stop
        } else if let vessel = p.onVessel {
            let key = s.lastEventNoteCode == "loaded_on_vessel" ? "live.vesselLeg" : "live.ferryLeg"
            leg = labels.text(key, ["from": name(p.fromCode), "to": name(p.toCode), "vessel": vessel])
            phase = .sea
        } else {
            leg = "\(name(p.fromCode)) → \(name(p.toCode))"
            phase = p.mode?.known == .sea ? .sea : .rail
        }
        var status = labels.state(s)
        if s.isDelayed { status += " · +\(labels.hours(s.delayHours))" }
        return LiveStatus(
            ref: s.ref, leg: leg, status: status, eta: s.eta, delayHours: s.delayHours,
            progress: delivered ? 1 : min(max(s.progress, 0), 1), tone: s.tone, phase: phase,
            delivered: delivered)
    }
}
