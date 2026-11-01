import MCCore
import SwiftUI
import UIKit

/// Лента точек маршрута: сплошная линия — пройдено, пунктир — впереди (как на карте).
/// Пройденные и дальние точки свёрнуты (`CheckpointWindow`), нажатие разворачивает всё.
struct CheckpointTimelineSection: View {
    let shipment: Shipment
    let labels: Labels
    @Environment(\.l10n) private var l
    @State private var expanded = false

    var body: some View {
        let points = shipment.checkpoints
        let window = CheckpointWindow(points)
        let range = expanded ? 0...max(points.count - 1, 0) : window.visible
        Section(l("card.route")) {
            if !points.isEmpty {
                if !expanded && window.hiddenBefore > 0 {
                    expandButton(
                        marker: .done,
                        title: l("timeline.passed", ["count": String(window.hiddenBefore)]),
                        subtitle: "\(labels.checkpoint(points[0])) — \(labels.checkpoint(points[window.hiddenBefore - 1]))",
                        top: nil, bottom: connector(to: window.visible.lowerBound, in: points))
                }
                ForEach(range, id: \.self) { index in
                    row(index, in: points)
                }
                if !expanded && window.hiddenAfter > 0 {
                    let first = window.visible.upperBound + 1
                    expandButton(
                        marker: .planned,
                        title: l("timeline.more", ["count": String(window.hiddenAfter)]),
                        subtitle: "\(labels.checkpoint(points[first])) — \(labels.checkpoint(points[points.count - 1]))",
                        top: connector(to: first, in: points), bottom: nil)
                }
            }
        }
    }

    private func row(_ index: Int, in points: [Checkpoint]) -> some View {
        let checkpoint = points[index]
        let state = checkpoint.state.known
        let marker: TimelineRow.Marker =
            switch state {
            case .done: .done
            case .current: .current
            case .planned, nil: .planned
            }
        let late = checkpoint.actualAt.map { $0.timeIntervalSince(checkpoint.plannedAt) / 3600 }
        let time = checkpoint.actualAt.map { l("card.fact", ["ts": l.dateTime($0)]) }
            ?? l("card.plan", ["ts": l.dateTime(checkpoint.plannedAt)])
        return TimelineRow(
            marker: marker,
            tone: Theme.tone(shipment.tone),
            title: labels.checkpoint(checkpoint),
            subtitle: time,
            note: state == .current ? labels.hold(shipment) : nil,
            badge: (late ?? 0) >= 1 ? "+\(l.hours(late ?? 0))" : nil,
            top: index > 0 ? connector(to: index, in: points) : nil,
            bottom: index < points.count - 1 ? connector(to: index + 1, in: points) : nil
        )
        .timelineRowStyle()
    }

    private func expandButton(
        marker: TimelineRow.Marker, title: String, subtitle: String,
        top: TimelineRow.Connector?, bottom: TimelineRow.Connector?
    ) -> some View {
        Button {
            withAnimation { expanded = true }
        } label: {
            TimelineRow(
                marker: marker, tone: Theme.tone(shipment.tone), title: title, subtitle: subtitle,
                note: nil, badge: nil, top: top, bottom: bottom, showsChevron: true
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("timeline.expand")
        .timelineRowStyle()
    }

    /// Линия к точке: пройденный путь (точка пройдена или текущая) — сплошная, впереди — пунктир.
    private func connector(to index: Int, in points: [Checkpoint]) -> TimelineRow.Connector {
        switch points[index].state.known {
        case .done, .current: .solid
        case .planned, nil: .dashed
        }
    }
}

/// Строка ленты: значок с линиями сверху и снизу, название, время, причина стоянки, опоздание.
struct TimelineRow: View {
    enum Marker { case done, current, planned }
    enum Connector { case solid, dashed }

    let marker: Marker
    let tone: Color
    let title: String
    let subtitle: String
    let note: String?
    let badge: String?
    let top: Connector?
    let bottom: Connector?
    var showsChevron = false
    @ScaledMetric(relativeTo: .body) private var iconSize: CGFloat = 20

    var body: some View {
        HStack(spacing: 12) {
            icon
                .frame(width: iconSize, height: iconSize)
                .background(Circle().fill(Color(uiColor: .secondarySystemGroupedBackground)))
                .frame(maxHeight: .infinity)
                .background {
                    VStack(spacing: 0) {
                        line(top)
                        line(bottom)
                    }
                }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).fontWeight(marker == .current ? .semibold : .regular)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let note {
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(Theme.warning)
                }
            }
            .padding(.vertical, 10)
            Spacer(minLength: 0)
            if let badge {
                Text(badge)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.warning)
            }
            if showsChevron {
                Image(systemName: "chevron.down")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var icon: some View {
        switch marker {
        case .done: Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.ok)
        case .current: Image(systemName: "circle.inset.filled").foregroundStyle(tone)
        case .planned: Image(systemName: "circle").foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func line(_ connector: Connector?) -> some View {
        switch connector {
        case .solid:
            Rectangle().fill(Theme.ok).frame(width: 2)
        case .dashed:
            VerticalLine()
                .stroke(.secondary, style: StrokeStyle(lineWidth: 2, dash: [3, 3]))
                .frame(width: 2)
        case nil:
            Color.clear.frame(width: 2)
        }
    }
}

private struct VerticalLine: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        return path
    }
}

extension View {
    /// Строка ленты во всю высоту: без полей сверху/снизу и разделителей — линии непрерывны.
    fileprivate func timelineRowStyle() -> some View {
        listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 16))
            .listRowSeparator(.hidden)
    }
}
