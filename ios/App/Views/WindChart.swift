import Charts
import MCCore
import SwiftUI

/// Почасовой ветер: скорость — линия, порывы — пунктир. Над порогами — подписанные зоны
/// «риск» и «остановка» (разный пунктир: не только оттенок), «сейчас», выбор часа пальцем
/// и вывод одной строкой под графиком. Аудиографик VoiceOver строит сам Swift Charts.
struct WindChart: View {
    let hours: [WindHour]
    let thresholds: Thresholds?
    let now: Date
    @Environment(\.l10n) private var l
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var height: CGFloat = 180
    @State private var selected: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            legend
            chart
            outlookText
        }
    }

    private var legend: some View {
        HStack(spacing: 12) {
            Text(l("chart.unit"))
            Spacer()
            HStack(spacing: 4) {
                Capsule().fill(Theme.accent).frame(width: 14, height: 2)
                Text(l("chart.speed"))
            }
            HStack(spacing: 4) {
                Line()
                    .stroke(.secondary, style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    .frame(width: 14, height: 1)
                Text(l("chart.gust"))
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }

    private var chart: some View {
        let yMax = max((hours.map(\.gust).max() ?? 0) + 2, (thresholds?.criticalWind ?? 0) + 4)
        let first = hours.first?.ts ?? now
        let last = hours.last?.ts ?? now
        return Chart {
            if let thresholds {
                RectangleMark(
                    xStart: .value("t", first), xEnd: .value("t", last),
                    yStart: .value("y", thresholds.warningWind), yEnd: .value("y", thresholds.criticalWind)
                )
                .foregroundStyle(Theme.warning.opacity(0.10))
                RectangleMark(
                    xStart: .value("t", first), xEnd: .value("t", last),
                    yStart: .value("y", thresholds.criticalWind), yEnd: .value("y", yMax)
                )
                .foregroundStyle(Theme.critical.opacity(0.10))
                RuleMark(y: .value(l("level.warning"), thresholds.warningWind))
                    .foregroundStyle(Theme.warning)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .annotation(position: .bottom, alignment: .trailing) {
                        Text(l("chart.risk")).font(.caption2.weight(.semibold)).foregroundStyle(Theme.warning)
                    }
                RuleMark(y: .value(l("level.critical"), thresholds.criticalWind))
                    .foregroundStyle(Theme.critical)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [6, 3]))
                    .annotation(position: .top, alignment: .trailing) {
                        Text(l("chart.stop")).font(.caption2.weight(.semibold)).foregroundStyle(Theme.critical)
                    }
            }
            ForEach(hours, id: \.ts) { hour in
                LineMark(x: .value("t", hour.ts), y: .value(l("chart.speed"), hour.speed), series: .value("s", "speed"))
                    .foregroundStyle(Theme.accent)
                    .interpolationMethod(.monotone)
                LineMark(x: .value("t", hour.ts), y: .value(l("chart.gust"), hour.gust), series: .value("s", "gust"))
                    .foregroundStyle(.secondary)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    .interpolationMethod(.monotone)
            }
            RuleMark(x: .value(l("card.now"), now))
                .foregroundStyle(Color.primary.opacity(0.35))
            if let hour = selectedHour {
                RuleMark(x: .value("t", hour.ts))
                    .foregroundStyle(Color.primary)
                    .annotation(position: .top, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        callout(hour)
                    }
                PointMark(x: .value("t", hour.ts), y: .value(l("chart.speed"), hour.speed))
                    .foregroundStyle(Theme.accent)
            }
        }
        .chartYScale(domain: 0...yMax)
        .chartYAxisLabel(l("chart.unit"))
        .chartXSelection(value: $selected)
        .chartXAxis {
            // на крупном шрифте подписи по 12 часов налезают друг на друга
            AxisMarks(values: .stride(by: .hour, count: typeSize.isAccessibilitySize ? 24 : 12)) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        VStack(spacing: 0) {
                            Text(date, format: .dateTime.day().month(.abbreviated).locale(l.locale))
                            Text(date, format: .dateTime.hour(.twoDigits(amPM: .omitted)).minute(.twoDigits).locale(l.locale))
                        }
                    }
                }
            }
        }
        .frame(height: height)
        .accessibilityIdentifier("wind.chart")
    }

    /// Ближайший к пальцу час прогноза.
    private var selectedHour: WindHour? {
        guard let selected else { return nil }
        return hours.min { abs($0.ts.timeIntervalSince(selected)) < abs($1.ts.timeIntervalSince(selected)) }
    }

    private func callout(_ hour: WindHour) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(l.dateTime(hour.ts)).font(.caption2).foregroundStyle(.secondary)
            Text(l("chart.callout", [
                "speed": String(Int(hour.speed.rounded())),
                "gust": String(Int(hour.gust.rounded())),
            ]))
            .font(.caption.weight(.semibold))
            .monospacedDigit()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    /// «Вероятна остановка весь прогноз» / «Риск остановки до 1 нояб., 14:00» / «Ветер до 9 м/с».
    @ViewBuilder
    private var outlookText: some View {
        let outlook = WindOutlook(hours: hours, now: now)
        let peak = String(Int(outlook.peak.rounded()))
        switch outlook.level {
        case .critical?, .warning?:
            let level = outlook.level ?? .warning
            let key = outlook.until == nil ? "chart.outlook.whole" : "chart.outlook.until"
            Label(
                l(key, [
                    "level": l("level.\(level.rawValue)"),
                    "until": outlook.until.map(l.dateTime) ?? "",
                    "max": peak,
                ]),
                systemImage: "exclamationmark.triangle.fill"
            )
            .font(.subheadline)
            .foregroundStyle(Theme.level(level))
            .accessibilityIdentifier("wind.outlook")
        case .watch?, nil:
            Text(l("chart.summary", ["max": peak]))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("wind.outlook")
        }
    }
}

private struct Line: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        return path
    }
}
