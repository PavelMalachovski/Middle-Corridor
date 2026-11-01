import MCCore
import SwiftUI

/// Вкладка «Коридор»: обзорная карта, порты с риском и ветром, неделя, новости.
struct CorridorView: View {
    let store: TrackedShipments
    @Environment(\.l10n) private var l
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            List {
                if store.lastError != nil {
                    Section { OfflineBanner(updatedAt: store.updatedAt) }
                }
                if let snapshot = store.snapshot {
                    Section {
                        CorridorMapView(snapshot: snapshot)
                    }
                    ports(snapshot)
                    week(snapshot)
                    news(snapshot)
                } else if store.lastError == nil {
                    Section { ProgressView().frame(maxWidth: .infinity) }
                }
            }
            .navigationTitle(l("tab.corridor"))
            .navigationDestination(for: String.self) { code in
                PortDetailView(code: code, store: store)
            }
            .refreshable { await store.refresh() }
            // первый запуск: переключились сюда, пока шло первое обновление (оно отменилось)
            .task { if store.snapshot == nil { await store.refresh() } }
        }
    }

    private func ports(_ snapshot: MapSnapshot) -> some View {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        let ports = snapshot.nodes
            .filter { $0.kind.known == .port }
            .sorted {
                let a = $0.alertLevel?.known, b = $1.alertLevel?.known
                if a != b { return (a.map { $0.rank } ?? -1) > (b.map { $0.rank } ?? -1) }
                return (labels.node($0.code) ?? $0.name) < (labels.node($1.code) ?? $1.name)
            }
        return Section(l("corridor.ports")) {
            ForEach(ports) { node in
                NavigationLink(value: node.code) {
                    PortRow(node: node, name: labels.node(node.code) ?? node.name)
                }
                .accessibilityIdentifier("port.\(node.code)")
            }
        }
    }

    @ViewBuilder
    private func week(_ snapshot: MapSnapshot) -> some View {
        if let summary = snapshot.summary {
            Section(l("corridor.week")) {
                LabeledContent(l("corridor.crossings"), value: String(summary.caspianCrossings))
                if let downtime = summary.portDowntimeHours {
                    LabeledContent(l("corridor.downtime"), value: l.hours(downtime))
                }
                if let delay = summary.avgDelayHours {
                    LabeledContent(l("corridor.avgDelay"), value: l.hours(delay))
                }
            }
        }
    }

    @ViewBuilder
    private func news(_ snapshot: MapSnapshot) -> some View {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        if !snapshot.news.isEmpty {
            Section {
                ForEach(snapshot.news) { item in
                    Button {
                        if let url = URL(string: item.url) { openURL(url) }
                    } label: {
                        HStack(alignment: .firstTextBaseline) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.title).foregroundStyle(.primary)
                                HStack(spacing: 4) {
                                    Text(item.source)
                                    if let at = item.publishedAt {
                                        Text("·")
                                        Text(labels.relative(at, to: snapshot.serverTime))  // часы сервера, не телефона
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 0)
                            // ссылка уводит в Safari — это видно заранее
                            Image(systemName: "arrow.up.right")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.tertiary)
                                .accessibilityHidden(true)
                        }
                    }
                }
            } header: {
                Text(l("corridor.news")).accessibilityIdentifier("corridor.news")
            }
        }
    }
}

/// Строка порта: имя, уровень риска «пилюлей» («спокойно» или «нет данных» — тоже явно),
/// направление и сила ветра.
struct PortRow: View {
    let node: NodeStatus
    let name: String
    @Environment(\.l10n) private var l

    var body: some View {
        let labels = Labels(lang: l.lang, nodes: [])
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(name).bold()
                Spacer()
                levelPill
            }
            if let speed = node.windSpeed {
                HStack(spacing: 5) {
                    if let dir = node.windDir {
                        // стрелка — куда дует, буквы — откуда (метеорологический румб)
                        Image(systemName: "arrow.up")
                            .font(.caption.weight(.bold))
                            .rotationEffect(.degrees(dir + 180))
                            .accessibilityHidden(true)
                        Text(labels.compass(dir))
                        Text("·")
                    }
                    Text(l("corridor.windShort", [
                        "speed": String(Int(speed.rounded())),
                        "gust": String(Int((node.windGust ?? speed).rounded())),
                    ]))
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            } else {
                Text(l("corridor.noWind"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var levelPill: some View {
        if let level = node.alertLevel?.known {
            pill(l("level.\(level.rawValue)"), color: Theme.level(level), symbol: level >= .warning ? "exclamationmark.triangle.fill" : nil)
        } else if node.windSpeed != nil {
            pill(l("corridor.calm.short"), color: Theme.ok, symbol: nil)
        } else {
            pill(l("corridor.noData"), color: .primary, symbol: nil, neutral: true)
        }
    }

    private func pill(_ text: String, color: Color, symbol: String?, neutral: Bool = false) -> some View {
        HStack(spacing: 3) {
            if let symbol { Image(systemName: symbol).imageScale(.small) }
            Text(text)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(color)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(neutral ? Color.primary.opacity(0.08) : color.opacity(0.10), in: Capsule())
    }
}
