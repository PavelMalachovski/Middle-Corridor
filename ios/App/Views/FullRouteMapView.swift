import MCCore
import MapKit
import SwiftUI

/// Полноэкранная карта маршрута, как в Telegram: масштаб щипком, перетаскивание, поворот;
/// кнопки «Весь маршрут» и «Где груз». Пройденное — линия, впереди — пунктир, проекция — контур.
struct FullRouteMapView: View {
    let shipment: Shipment
    let nodes: [NodeStatus]
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var position: MapCameraPosition = .automatic

    var body: some View {
        let parts = RouteGeometry.split(track: shipment.track, at: shipment.position, state: shipment.state.known)
        let here = CLLocationCoordinate2D(latitude: shipment.position.lat, longitude: shipment.position.lon)
        let tone = Theme.tone(shipment.tone)
        let byCode = Dictionary(nodes.map { ($0.code, $0) }, uniquingKeysWith: { first, _ in first })
        let labels = Labels(lang: l.lang, nodes: nodes)
        Map(position: $position) {
            if parts.done.count > 1 {
                MapPolyline(coordinates: parts.done.map(\.coordinate)).stroke(tone, lineWidth: 5)
            }
            if parts.rest.count > 1 {
                MapPolyline(coordinates: parts.rest.map(\.coordinate))
                    .stroke(.secondary, style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [7, 6]))
            }
            ForEach(shipment.checkpoints.filter { byCode[$0.code]?.kind.known == .port }, id: \.code) { checkpoint in
                let node = byCode[checkpoint.code]
                Annotation(
                    labels.checkpoint(checkpoint),
                    coordinate: CLLocationCoordinate2D(latitude: checkpoint.lat, longitude: checkpoint.lon)
                ) {
                    Circle()
                        .fill(Theme.level(node?.alertLevel?.known))
                        .frame(width: 12, height: 12)
                        .overlay(Circle().stroke(.background, lineWidth: 2))
                }
            }
            Annotation(shipment.ref, coordinate: here) {
                if shipment.position.confirmed {
                    Circle().fill(tone).frame(width: 20, height: 20).overlay(Circle().stroke(.white, lineWidth: 3))
                } else {
                    Circle().stroke(tone, style: StrokeStyle(lineWidth: 3, dash: [3, 2]))
                        .background(Circle().fill(.background))
                        .frame(width: 20, height: 20)
                }
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
        .mapControls {
            MapCompass()
            MapScaleView()
        }
        .accessibilityIdentifier("map.full")
        .onAppear { position = .rect(RouteMapView.rect(parts.done + parts.rest)) }
        .overlay(alignment: .topTrailing) {
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.headline).padding(12)
            }
            .buttonStyle(.bordered)
            .buttonBorderShape(.circle)
            .padding()
            .accessibilityLabel(l("map.close"))
            .accessibilityIdentifier("map.close")
        }
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: 12) {
                Button {
                    withAnimation { position = .rect(RouteMapView.rect(parts.done + parts.rest)) }
                } label: {
                    Label(l("map.fitRoute"), systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                }
                .accessibilityIdentifier("map.fitRoute")
                Button {
                    withAnimation { position = .camera(MapCamera(centerCoordinate: here, distance: 900_000)) }
                } label: {
                    Label(l("map.whereNow"), systemImage: "location.fill")
                }
                .accessibilityIdentifier("map.whereNow")
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accentStrong)
            .padding(.bottom, 8)
        }
    }
}
