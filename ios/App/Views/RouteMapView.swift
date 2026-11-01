import MCCore
import MapKit
import SwiftUI

/// Карта маршрута в карточке: пройденное — сплошной линией, оставшееся — пунктиром;
/// точка «где сейчас» залита, если положение подтверждено, и контурная, если это оценка.
struct RouteMapView: View {
    let shipment: Shipment
    @Environment(\.l10n) private var l

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
                    .stroke(Color.gray, style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [6, 5]))
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
        .frame(height: 220)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(l("card.mapLabel"))
        .accessibilityIdentifier("card.map")
    }

    /// Рамка всего трека с полями, чтобы линия не упиралась в края.
    private static func rect(_ points: [GeoPoint]) -> MKMapRect {
        let mapPoints = points.map { MKMapPoint($0.coordinate) }
        guard let first = mapPoints.first else { return .world }
        var rect = MKMapRect(origin: first, size: MKMapSize(width: 0, height: 0))
        for point in mapPoints.dropFirst() {
            rect = rect.union(MKMapRect(origin: point, size: MKMapSize(width: 0, height: 0)))
        }
        let pad = max(rect.size.width, rect.size.height) * 0.08
        return rect.insetBy(dx: -pad, dy: -pad)
    }
}

extension GeoPoint {
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: lat, longitude: lon) }
}
