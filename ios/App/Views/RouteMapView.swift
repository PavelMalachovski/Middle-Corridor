import MCCore
import MapKit
import SwiftUI

/// Карта маршрута: пройденное — сплошной линией цвета тона, оставшееся — пунктиром;
/// точка «где сейчас» залита, если положение подтверждено, и контурная, если это оценка.
/// Порты на пути — точками цвета риска. Превью неподвижно; нажатие — `FullRouteMapView`.
struct RouteMapView: View {
    let shipment: Shipment
    var nodes: [NodeStatus] = []
    @Environment(\.l10n) private var l
    @ScaledMetric(relativeTo: .body) private var height: CGFloat = 220
    @State private var showFull = false

    var body: some View {
        let parts = RouteGeometry.split(track: shipment.track, at: shipment.position, state: shipment.state.known)
        let here = CLLocationCoordinate2D(latitude: shipment.position.lat, longitude: shipment.position.lon)
        let tone = Theme.tone(shipment.tone)
        Map(initialPosition: .rect(Self.rect(parts.done + parts.rest)), interactionModes: []) {
            if parts.done.count > 1 {
                MapPolyline(coordinates: parts.done.map(\.coordinate))
                    .stroke(tone, lineWidth: 4)
            }
            if parts.rest.count > 1 {
                MapPolyline(coordinates: parts.rest.map(\.coordinate))
                    .stroke(.secondary, style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [6, 5]))
            }
            ForEach(ports) { port in
                Annotation(
                    "",
                    coordinate: CLLocationCoordinate2D(latitude: port.node.lat, longitude: port.node.lon)
                ) {
                    Circle()
                        .fill(port.color)
                        .frame(width: 10, height: 10)
                        .overlay(Circle().stroke(.white, lineWidth: 1.5))
                }
            }
            Annotation("", coordinate: here) {
                if shipment.position.confirmed {
                    Circle().fill(tone).frame(width: 16, height: 16)
                        .overlay(Circle().stroke(.white, lineWidth: 2))
                } else {
                    Circle().stroke(tone, style: StrokeStyle(lineWidth: 3, dash: [3, 2]))
                        .background(Circle().fill(.background))
                        .frame(width: 16, height: 16)
                }
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
        .frame(height: height)
        .overlay {
            // превью не двигается (жесты спорят с прокруткой списка) — нажатие открывает карту целиком
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture { showFull = true }
        }
        .overlay(alignment: .bottomTrailing) {
            Label(l("card.openMap"), systemImage: "arrow.up.left.and.arrow.down.right")
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(.regularMaterial, in: Capsule())
                .padding(10)
                .allowsHitTesting(false)
        }
        .sheet(isPresented: $showFull) {
            FullRouteMapView(shipment: shipment, nodes: nodes)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText)
        .accessibilityHint(l("card.mapHint"))
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { showFull = true }
        .accessibilityIdentifier("card.map")
    }

    /// Карта для VoiceOver — смыслом: где груз и сколько пройдено.
    private var accessibilityText: String {
        let labels = Labels(lang: l.lang, nodes: nodes)
        return l("card.mapLabel.value", [
            "where": labels.position(shipment).title,
            "pct": String(Int((shipment.progress * 100).rounded())),
        ])
    }

    /// Порты впереди по маршруту (и где груз стоит) с цветом уровня риска; спокойные — `ok`.
    private var ports: [RoutePort] {
        let byCode = Dictionary(nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        let labels = Labels(lang: l.lang, nodes: nodes)
        return shipment.checkpoints
            .filter { $0.state.known != .done }
            .compactMap { checkpoint -> RoutePort? in
                guard let node = byCode[checkpoint.code], node.kind.known == .port, node.isWeatherTracked else {
                    return nil
                }
                let level = node.alertLevel?.known
                return RoutePort(node: node, name: labels.checkpoint(checkpoint), color: level.map { Theme.level($0) } ?? Theme.ok)
            }
    }

    /// Рамка всего трека с полями, чтобы линия не упиралась в края.
    static func rect(_ points: [GeoPoint], padding: Double = 0.08) -> MKMapRect {
        let mapPoints = points.map { MKMapPoint($0.coordinate) }
        guard let first = mapPoints.first else { return .world }
        var rect = MKMapRect(origin: first, size: MKMapSize(width: 0, height: 0))
        for point in mapPoints.dropFirst() {
            rect = rect.union(MKMapRect(origin: point, size: MKMapSize(width: 0, height: 0)))
        }
        let pad = max(rect.size.width, rect.size.height) * padding
        return rect.insetBy(dx: -pad, dy: -pad)
    }
}

private struct RoutePort: Identifiable {
    var id: String { node.code }
    let node: NodeStatus
    let name: String
    let color: Color
}

extension GeoPoint {
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: lat, longitude: lon) }
}
