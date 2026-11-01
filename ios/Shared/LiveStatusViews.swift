import MCCore
import SwiftUI
import WidgetKit

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

    /// «Прибытие» / «ETA» — из MCCore, а не тернарником в коде вида.
    static func etaLabel(_ lang: Lang) -> String {
        Labels(lang: lang, nodes: []).text("widget.eta")
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
                Text(LiveStatusStyle.etaLabel(lang)).font(.caption2).foregroundStyle(.secondary)
                Text(LiveStatusStyle.eta(status, lang: lang)).font(.caption.weight(.semibold))
            }
        }
    }
}

/// Содержимое виджета (small / medium); то же рисует предпросмотр в приложении.
struct ShipmentWidgetContent: View {
    let status: LiveStatus
    let lang: Lang
    let note: String?
    let family: WidgetFamilyKind

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: LiveStatusStyle.icon(status))
                Text(status.ref).font(.caption.weight(.bold)).lineLimit(1)
            }
            .foregroundStyle(Theme.tone(status.tone))
            .widgetAccentable()  // тонированный домашний экран (iOS 18+): номер — акцентом
            Text(status.status)
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.tone(status.tone))
                .lineLimit(1)
            Text(status.leg).font(family == .medium ? .subheadline : .caption).lineLimit(2)
            Spacer(minLength: 0)
            ProgressView(value: status.progress).tint(Theme.tone(status.tone))
            HStack {
                Text(LiveStatusStyle.etaLabel(lang)).foregroundStyle(.secondary)
                Spacer(minLength: 2)
                Text(LiveStatusStyle.etaShort(status, lang: lang))
            }
            .font(.caption2)
            if let note { Text(note).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
        }
    }
}

/// Размер виджета без WidgetKit (приложению предпросмотра он не нужен).
enum WidgetFamilyKind {
    case small, medium
}
