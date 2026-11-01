import MCCore
import SwiftUI

/// Первый блок карточки груза — ответ без прокрутки: статус, когда прибудет, насколько позже плана,
/// где сейчас и почему стоит, когда выйдет из очереди.
struct ShipmentHeroSection: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let s = shipment
        Section {
            summary(s)
            position(s)
            if let queue = s.queue {
                QueueRow(queue: queue, labels: labels)
            }
        }
    }

    private func summary(_ s: Shipment) -> some View {
        let delivered = s.state.known == .delivered
        let pct = String(Int((s.progress * 100).rounded()))
        return VStack(alignment: .leading, spacing: 6) {
            // не влезает в строку (крупный шрифт) — маршрут под статусом, а не «Сиань → Ко…»
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline) {
                    StatusPill(shipment: s, labels: labels)
                    Spacer()
                    routeText(s).lineLimit(1)
                }
                VStack(alignment: .leading, spacing: 4) {
                    StatusPill(shipment: s, labels: labels)
                    routeText(s)
                }
            }
            Text(l(delivered ? "hero.arrived" : "hero.eta"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .padding(.top, 4)
            // вилка «6–9 нояб.», если плохой сценарий заметно позже; иначе одна дата со временем
            let range = delivered ? nil : s.eta.flatMap { labels.etaRange($0, s.etaLatest) }
            Text(range ?? s.eta.map(l.dateTime) ?? "—")
                .font(.title.bold())
                .monospacedDigit()
                .contentTransition(.numericText())
            if range != nil, let eta = s.eta, let latest = s.etaLatest {
                Text(l("card.etaRange", ["usual": l.dateTime(eta), "worst": l.dateTime(latest)]))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if s.isDelayed {
                Text(l("hero.late", ["value": l.hours(s.delayHours)]))
                    .font(.subheadline)
                    .foregroundStyle(Theme.warning)
                    .contentTransition(.numericText())
            }
            ProgressView(value: min(max(s.progress, 0), 1))
                .tint(Theme.tone(s.tone))
                .padding(.top, 4)
            // «Сиань · 70% · Констанца»; на крупном шрифте — только процент (концы маршрута уже выше)
            ViewThatFits(in: .horizontal) {
                HStack {
                    Text(labels.node(s.originCode) ?? s.origin)
                    Spacer()
                    Text(l("card.progress", ["pct": pct])).monospacedDigit()
                    Spacer()
                    Text(labels.node(s.destinationCode) ?? s.destination)
                }
                .lineLimit(1)
                Text(l("card.progress", ["pct": pct])).monospacedDigit()
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
        .animation(.default, value: s.eta)
        .animation(.default, value: s.delayHours)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("card.eta")
    }

    private func routeText(_ s: Shipment) -> some View {
        Text(labels.route(s))
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    /// Где груз сейчас. Оценка по расписанию — курсивом и с меткой «≈ оценка»: это не факт.
    private func position(_ s: Shipment) -> some View {
        let position = labels.position(s)
        return VStack(alignment: .leading, spacing: 4) {
            if let hold = labels.hold(s) {
                Label(hold, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(Theme.warning)
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("hold")
            }
            Text(position.title)
                .italic(!position.confirmed)
                .foregroundStyle(position.confirmed ? .primary : .secondary)
                .accessibilityIdentifier("card.position")
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if !position.confirmed {
                    Label(l("card.estimateBadge"), systemImage: "circle.dashed")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                Text(position.detail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Text(labels.event(s) + (s.lastEventAt.map { " · " + l.dateTime($0) } ?? ""))
                .font(.caption)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("card.event")
        }
        .padding(.vertical, 2)
    }
}

/// Прогноз выхода из очереди: ожидаемо, плохой сценарий, место и темп отгрузки.
struct QueueRow: View {
    let queue: QueueForecast
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        let text = labels.queue(queue)
        VStack(alignment: .leading, spacing: 4) {
            Text(l("card.queue", ["port": labels.node(queue.portCode) ?? queue.portCode]))
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(l("queue.main", ["value": text.main])).font(.headline)
            Text(l("queue.worst", ["value": text.worst])).foregroundStyle(.secondary)
            Text(l("queue.place", [
                "position": String(queue.position),
                "perDay": String(Int(queue.perDay.rounded())),
            ]))
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("card.queue")
    }
}
