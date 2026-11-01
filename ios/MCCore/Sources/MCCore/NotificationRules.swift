import Foundation

/// Виды уведомлений; у каждого — свой переключатель в настройках.
public enum NoticeKind: String, CaseIterable, Sendable {
    case storm, event, delay, queue
}

public struct NotifySettings: Sendable, Equatable {
    public var storm: Bool
    public var event: Bool
    public var delay: Bool
    public var queue: Bool

    public init(storm: Bool, event: Bool, delay: Bool, queue: Bool) {
        self.storm = storm
        self.event = event
        self.delay = delay
        self.queue = queue
    }

    public static let all = NotifySettings(storm: true, event: true, delay: true, queue: true)

    public func allows(_ kind: NoticeKind) -> Bool {
        switch kind {
        case .storm: storm
        case .event: event
        case .delay: delay
        case .queue: queue
        }
    }
}

/// Уведомление для пользователя; `id` детерминирован — одно и то же не придёт дважды.
public struct AppNotice: Sendable, Equatable, Identifiable {
    public let id: String
    public let kind: NoticeKind
    public let ref: String
    public let title: String
    public let body: String
}

/// Что изменилось между двумя обновлениями — и о чём стоит сказать.
/// Первая загрузка груза (старых данных нет) уведомлений не даёт.
public enum NotificationRules {
    /// Задержка выросла хотя бы на столько часов.
    public static let delayStepHours = 3.0
    /// Прогноз выхода из очереди сдвинулся хотя бы на столько часов.
    public static let queueStepHours = 12.0

    public static func diff(
        old: [String: Shipment],
        new: [String: Shipment],
        oldNodes: [NodeStatus],
        newNodes: [NodeStatus],
        settings: NotifySettings,
        labels: Labels
    ) -> [AppNotice] {
        let oldLevels = levels(oldNodes)
        let newByCode = Dictionary(newNodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        var notices: [AppNotice] = []
        for ref in new.keys.sorted() {
            guard let now = new[ref], let before = old[ref] else { continue }
            if settings.storm {
                notices += storms(now, oldLevels: oldLevels, newNodes: newByCode, labels: labels)
            }
            if settings.event, now.lastEventAt != before.lastEventAt || now.lastEvent != before.lastEvent {
                let stamp = Int(now.lastEventAt?.timeIntervalSince1970 ?? 0)
                notices.append(
                    AppNotice(
                        id: "event-\(ref)-\(stamp)", kind: .event, ref: ref,
                        title: "\(ref): \(labels.event(now))",
                        body: eventBody(now, labels: labels)))
            }
            if settings.delay, now.isDelayed, now.delayHours - before.delayHours >= delayStepHours {
                notices.append(
                    AppNotice(
                        id: "delay-\(ref)-\(Int(now.delayHours))", kind: .delay, ref: ref,
                        title: labels.text("notice.delay.title", ["ref": ref, "hours": labels.hours(now.delayHours)]),
                        body: labels.hold(now) ?? labels.route(now)))
            }
            if settings.queue, let queue = now.queue,
                before.queue.map({ abs(queue.p50Hours - $0.p50Hours) >= queueStepHours }) ?? true
            {
                let text = labels.queue(queue)
                notices.append(
                    AppNotice(
                        id: "queue-\(ref)-\(Int(queue.p50Hours))", kind: .queue, ref: ref,
                        title: labels.text("notice.queue.title", ["ref": ref, "main": text.main]),
                        body: labels.text("notice.queue.body", ["worst": text.worst])))
            }
        }
        return notices
    }

    /// Порты на пути груза (от текущего узла включительно), где риск вырос до warning и выше.
    private static func storms(
        _ s: Shipment, oldLevels: [String: AlertLevel], newNodes: [String: NodeStatus], labels: Labels
    ) -> [AppNotice] {
        let standing = s.position.mode == nil ? s.position.fromCode : nil
        var codes: [String] = standing.map { [$0] } ?? []
        for checkpoint in s.checkpoints where checkpoint.state.known != .done && !codes.contains(checkpoint.code) {
            codes.append(checkpoint.code)
        }
        return codes.compactMap { code in
            guard let node = newNodes[code], node.isWeatherTracked,
                let level = node.alertLevel?.known, level >= .warning,
                oldLevels[code].map({ level > $0 }) ?? true
            else { return nil }
            let port = labels.node(code) ?? node.name
            return AppNotice(
                id: "storm-\(s.ref)-\(code)-\(level.rawValue)", kind: .storm, ref: s.ref,
                title: labels.text("notice.storm.title", ["port": port, "level": labels.text("level.\(level.rawValue)")]),
                body: labels.text(code == standing ? "notice.storm.here" : "notice.storm.ahead", ["ref": s.ref]))
        }
    }

    private static func eventBody(_ s: Shipment, labels: Labels) -> String {
        guard let eta = s.eta, s.state.known != .delivered else { return labels.route(s) }
        return labels.text("notice.event.body", ["route": labels.route(s), "eta": labels.dateTime(eta)])
    }

    private static func levels(_ nodes: [NodeStatus]) -> [String: AlertLevel] {
        var out: [String: AlertLevel] = [:]
        for node in nodes {
            if let level = node.alertLevel?.known, out[node.code] == nil { out[node.code] = level }
        }
        return out
    }
}
