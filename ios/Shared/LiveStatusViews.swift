import MCCore
import SwiftUI

/// Общие виды статуса груза: экран блокировки, Dynamic Island, виджет и предпросмотр в приложении.
enum LiveStatusStyle {
    static func icon(_ status: LiveStatus) -> String {
        switch status.phase {
        case .done: "checkmark.circle.fill"
        case .stop: "pause.circle.fill"
        case .sea: "ferry.fill"
        case .rail: "train.side.front.car"
        }
    }

    static func eta(_ status: LiveStatus, lang: Lang) -> String {
        guard let eta = status.eta else { return "—" }
        return eta.formatted(.dateTime.day().month(.abbreviated).hour().minute().locale(Locale(identifier: lang.rawValue)))
    }

    static func etaShort(_ status: LiveStatus, lang: Lang) -> String {
        guard let eta = status.eta else { return "—" }
        return eta.formatted(.dateTime.day().month(.abbreviated).locale(Locale(identifier: lang.rawValue)))
    }
}

/// Экран блокировки: номер, плечо, статус цветом, ETA, прогресс.
struct LiveStatusLockView: View {
    let status: LiveStatus
    let lang: Lang

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: LiveStatusStyle.icon(status))
                    .foregroundStyle(Theme.tone(status.tone))
                Text(status.ref).font(.headline)
                Spacer()
                Text(status.status)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.tone(status.tone))
            }
            Text(status.leg).font(.subheadline).lineLimit(2)
            HStack {
                ProgressView(value: status.progress).tint(Theme.tone(status.tone))
                Text(lang == .en ? "ETA" : "Прибытие").font(.caption2).foregroundStyle(.secondary)
                Text(LiveStatusStyle.eta(status, lang: lang)).font(.caption.weight(.semibold))
            }
        }
    }
}
