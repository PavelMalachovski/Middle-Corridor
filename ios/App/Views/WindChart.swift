import Charts
import MCCore
import SwiftUI

/// Почасовой ветер: скорость — линия, порывы — пунктир, пороги риска и остановки, «сейчас».
struct WindChart: View {
    let hours: [WindHour]
    let thresholds: Thresholds?
    let now: Date
    @Environment(\.l10n) private var l

    var body: some View {
        Chart {
            ForEach(hours, id: \.ts) { hour in
                LineMark(x: .value("t", hour.ts), y: .value(l("chart.speed"), hour.speed), series: .value("s", "speed"))
                    .foregroundStyle(Theme.accent)
                    .interpolationMethod(.monotone)
                LineMark(x: .value("t", hour.ts), y: .value(l("chart.gust"), hour.gust), series: .value("s", "gust"))
                    .foregroundStyle(Color.gray)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    .interpolationMethod(.monotone)
            }
            if let thresholds {
                RuleMark(y: .value(l("level.warning"), thresholds.warningWind))
                    .foregroundStyle(Theme.warning.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                RuleMark(y: .value(l("level.critical"), thresholds.criticalWind))
                    .foregroundStyle(Theme.critical.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
            }
            RuleMark(x: .value(l("card.now"), now))
                .foregroundStyle(Color.primary.opacity(0.35))
        }
        .chartYAxisLabel(l("chart.unit"))
        .chartXAxis {
            AxisMarks(values: .stride(by: .hour, count: 12)) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        VStack(spacing: 0) {
                            Text(date, format: .dateTime.day().month(.abbreviated).locale(l.locale))
                            Text(date, format: .dateTime.hour(.twoDigits(amPM: .omitted)).minute().locale(l.locale))
                        }
                    }
                }
            }
        }
        .frame(height: 180)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(summary)
        .accessibilityIdentifier("wind.chart")
    }

    private var summary: String {
        let ahead = hours.filter { $0.ts >= now }
        let peak = ahead.map(\.speed).max() ?? hours.map(\.speed).max() ?? 0
        return l("chart.summary", ["max": String(Int(peak.rounded()))])
    }
}
