import MCCore
import MapKit
import SwiftUI

/// Обзорная карта коридора: линии (рельсы — сплошные, паромы — пунктир), порты цветом риска,
/// остальные узлы — серыми точками. В списке карта неподвижна; нажатие открывает её целиком.
struct CorridorMapView: View {
    let snapshot: MapSnapshot
    @Environment(\.l10n) private var l
    @ScaledMetric(relativeTo: .body) private var height: CGFloat = 200
    @State private var showFull = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            CorridorMap(snapshot: snapshot, interactive: false)
                .frame(height: height)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .overlay {
                    Color.clear
                        .contentShape(Rectangle())
                        .onTapGesture { showFull = true }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(accessibilityText)
                .accessibilityAddTraits(.isButton)
                .accessibilityAction { showFull = true }
                .accessibilityIdentifier("corridor.map")
            legend
        }
        .padding(.vertical, 4)
        .fullScreenCover(isPresented: $showFull) {
            NavigationStack {
                CorridorMap(snapshot: snapshot, interactive: true)
                    .ignoresSafeArea(edges: .bottom)
                    .navigationTitle(l("tab.corridor"))
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button(l("settings.done")) { showFull = false }
                        }
                    }
            }
        }
    }

    /// Условные обозначения — только уровни, которые сейчас есть на карте, и «спокойно».
    private var legend: some View {
        let present = Set(snapshot.nodes.compactMap { $0.kind.known == .port ? $0.alertLevel?.known : nil })
        let levels = AlertLevel.allLevels.filter { present.contains($0) }
        return HStack(spacing: 12) {
            ForEach(levels, id: \.self) { level in
                dot(Theme.level(level), l("level.\(level.rawValue)"))
            }
            dot(Theme.ok, l("corridor.calm.short"))
            Spacer(minLength: 0)
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }

    private func dot(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(text).lineLimit(1)
        }
    }

    /// «Карта коридора. Вероятна остановка: Актау, Курык».
    private var accessibilityText: String {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        var parts = [l("corridor.mapLabel")]
        for level in AlertLevel.allLevels.reversed() {
            let names = snapshot.nodes
                .filter { $0.kind.known == .port && $0.alertLevel?.known == level }
                .map { labels.node($0.code) ?? $0.name }
            if !names.isEmpty {
                parts.append("\(l("level.\(level.rawValue)")): \(names.joined(separator: ", "))")
            }
        }
        return parts.joined(separator: ". ")
    }
}

/// Сама карта: на весь экран — интерактивная и с подписями портов.
private struct CorridorMap: View {
    let snapshot: MapSnapshot
    let interactive: Bool
    @Environment(\.l10n) private var l

    var body: some View {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        let segments = snapshot.segments ?? []
        Map(initialPosition: .rect(Self.rect(snapshot.nodes)), interactionModes: interactive ? .all : []) {
            ForEach(Array(segments.enumerated()), id: \.offset) { item in
                MapPolyline(coordinates: Self.coordinates(item.element))
                    .stroke(
                        .secondary,
                        style: StrokeStyle(
                            lineWidth: 2, lineCap: .round,
                            dash: item.element.mode.known == .sea ? [5, 4] : []))
            }
            ForEach(snapshot.nodes) { node in
                Annotation(
                    interactive && node.kind.known == .port ? (labels.node(node.code) ?? node.name) : "",
                    coordinate: CLLocationCoordinate2D(latitude: node.lat, longitude: node.lon)
                ) {
                    marker(node)
                }
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
    }

    /// Порт — цветом уровня риска (спокойный — `ok`), прочие узлы — маленькой серой точкой.
    @ViewBuilder
    private func marker(_ node: NodeStatus) -> some View {
        if node.kind.known == .port {
            Circle()
                .fill(node.alertLevel?.known.map { Theme.level($0) } ?? Theme.ok)
                .frame(width: 11, height: 11)
                .overlay(Circle().stroke(.white, lineWidth: 1.5))
        } else {
            Circle()
                .fill(.secondary)
                .frame(width: 5, height: 5)
        }
    }

    /// `[lon, lat]` бэкенда → координаты MapKit.
    private static func coordinates(_ segment: CorridorSegment) -> [CLLocationCoordinate2D] {
        segment.coordinates.compactMap { point in
            point.count >= 2 ? CLLocationCoordinate2D(latitude: point[1], longitude: point[0]) : nil
        }
    }

    private static func rect(_ nodes: [NodeStatus]) -> MKMapRect {
        let points = nodes.map { MKMapPoint(CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lon)) }
        guard let first = points.first else { return .world }
        var rect = MKMapRect(origin: first, size: MKMapSize(width: 0, height: 0))
        for point in points.dropFirst() {
            rect = rect.union(MKMapRect(origin: point, size: MKMapSize(width: 0, height: 0)))
        }
        let pad = max(rect.size.width, rect.size.height) * 0.05
        return rect.insetBy(dx: -pad, dy: -pad)
    }
}

extension AlertLevel {
    /// От слабого к сильному: усиление ветра → риск остановки → вероятна остановка.
    static let allLevels: [AlertLevel] = [.watch, .warning, .critical]
}
