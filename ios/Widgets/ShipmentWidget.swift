import AppIntents
import MCCore
import SwiftUI
import WidgetKit

struct ShipmentEntry: TimelineEntry {
    let date: Date
    let status: LiveStatus?
    let message: String?
    let lang: Lang
}

/// Таймлайн: одна запись, следующая — через 15 минут (и сразу, когда приложение просит перезагрузку).
struct ShipmentProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> ShipmentEntry {
        ShipmentEntry(date: .now, status: Self.sample, message: nil, lang: Self.lang)
    }

    func snapshot(for configuration: ShipmentWidgetIntent, in context: Context) async -> ShipmentEntry {
        context.isPreview ? placeholder(in: context) : await entry(for: configuration)
    }

    func timeline(for configuration: ShipmentWidgetIntent, in context: Context) async -> Timeline<ShipmentEntry> {
        Timeline(entries: [await entry(for: configuration)], policy: .after(.now.addingTimeInterval(15 * 60)))
    }

    private static var lang: Lang {
        if let raw = AppGroup.defaults?.string(forKey: AppGroup.langKey), let lang = Lang(rawValue: raw) {
            return lang
        }
        return Locale.preferredLanguages.first?.hasPrefix("ru") == true ? .ru : .en
    }

    private func entry(for configuration: ShipmentWidgetIntent) async -> ShipmentEntry {
        let lang = Self.lang
        let shared = AppGroup.defaults
        let cache = AppGroup.container.map { FileShipmentCache(directory: $0.appending(path: "cache")) }?.load()
        let ref = WidgetModel.resolve(
            intentRef: configuration.ref, sharedRef: shared?.string(forKey: AppGroup.refKey),
            cachedRefs: cache.map { Array($0.shipments.keys).sorted() } ?? [])
        guard let ref else {
            return ShipmentEntry(date: .now, status: nil, message: Labels(lang: lang, nodes: []).text("widget.choose"), lang: lang)
        }
        let server = configuration.server?.trimmingCharacters(in: .whitespaces).nilIfEmpty
            ?? shared?.string(forKey: AppGroup.serverKey) ?? "http://localhost:8000"
        var nodes = cache?.snapshot?.nodes ?? []
        if let url = URL(string: server) {
            let api = HTTPCorridorAPI(baseURL: url, timeout: 8)
            if nodes.isEmpty, let snapshot = try? await api.snapshot() { nodes = snapshot.nodes }
            if let shipment = try? await api.shipment(ref: ref) {
                let labels = Labels(lang: lang, nodes: nodes)
                return ShipmentEntry(date: .now, status: LiveStatus.make(shipment, labels: labels), message: nil, lang: lang)
            }
        }
        let labels = Labels(lang: lang, nodes: nodes)
        if let cached = cache?.shipments[ref] {  // нет связи — последнее известное
            return ShipmentEntry(
                date: .now, status: LiveStatus.make(cached, labels: labels), message: labels.text("widget.offline"), lang: lang)
        }
        return ShipmentEntry(date: .now, status: nil, message: labels.text("widget.offline"), lang: lang)
    }

    /// Для галереи виджетов и предпросмотра.
    static let sample = LiveStatus(
        ref: "MC-26-0398", leg: "Актау", status: "Стоянка · +18 ч", eta: .now.addingTimeInterval(5 * 86400),
        delayHours: 18, progress: 0.7, tone: .delayed, phase: .stop, delivered: false)
}

struct ShipmentWidgetView: View {
    let entry: ShipmentEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        if let status = entry.status {
            ShipmentWidgetContent(
                status: status, lang: entry.lang, note: entry.message, family: family == .systemMedium ? .medium : .small)
        } else {
            Text(entry.message ?? "")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }
}

struct ShipmentWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "shipment", intent: ShipmentWidgetIntent.self, provider: ShipmentProvider()) { entry in
            ShipmentWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Middle Corridor")
        .description("Статус груза")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

extension String {
    fileprivate var nilIfEmpty: String? { isEmpty ? nil : self }
}
