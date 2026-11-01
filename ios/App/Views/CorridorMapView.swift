import MCCore
import MapKit
import SwiftUI

/// Живая карта коридора: сегменты (ж/д — линия, море — пунктир), порты цветом риска,
/// паромы в эфире AIS (без позиции не рисуем: «нет данных», а не «стоит»), мои грузы.
/// Масштаб щипком и перетаскивание — как в Telegram.
struct CorridorMapView: View {
    let snapshot: MapSnapshot
    let mine: [Shipment]
    var identifier = "corridor.map"
    let onPort: (String) -> Void
    let onShipment: (String) -> Void
    @Environment(\.l10n) private var l
    @State private var position: MapCameraPosition = .automatic

    var body: some View {
        let labels = Labels(lang: l.lang, nodes: snapshot.nodes)
        Map(position: $position) {
            ForEach(Array((snapshot.segments ?? []).enumerated()), id: \.offset) { _, segment in
                let points = segment.coordinates.compactMap { $0.count >= 2 ? GeoPoint(lat: $0[1], lon: $0[0]) : nil }
                if segment.mode.known == .sea {
                    MapPolyline(coordinates: points.map(\.coordinate))
                        .stroke(Theme.accent.opacity(0.7), style: StrokeStyle(lineWidth: 2, dash: [5, 4]))
                } else {
                    MapPolyline(coordinates: points.map(\.coordinate)).stroke(.secondary, lineWidth: 2)
                }
            }
            ForEach(snapshot.nodes.filter { $0.kind.known == .port }) { node in
                Annotation(labels.node(node.code) ?? node.name, coordinate: .init(latitude: node.lat, longitude: node.lon)) {
                    Button { onPort(node.code) } label: {
                        Circle()
                            .fill(Theme.level(node.alertLevel?.known))
                            .frame(width: 16, height: 16)
                            .overlay(Circle().stroke(.background, lineWidth: 2))
                    }
                    .accessibilityIdentifier("port.pin.\(node.code)")
                }
            }
            ForEach(CorridorMap.liveVessels(snapshot.vessels ?? []), id: \.name) { vessel in
                Annotation(vessel.name, coordinate: .init(latitude: vessel.lat ?? 0, longitude: vessel.lon ?? 0)) {
                    Image(systemName: "location.north.fill")
                        .font(.caption)
                        .rotationEffect(.degrees(vessel.cog ?? 0))
                        .foregroundStyle(.primary)
                        .padding(4)
                        .background(.regularMaterial, in: Circle())
                }
            }
            ForEach(mine) { s in
                Annotation(s.ref, coordinate: .init(latitude: s.position.lat, longitude: s.position.lon)) {
                    Button { onShipment(s.ref) } label: {
                        Image(systemName: "shippingbox.fill")
                            .font(.caption)
                            .foregroundStyle(.white)
                            .padding(6)
                            .background(Theme.tone(s.tone), in: Circle())
                    }
                }
            }
        }
        .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
        .mapControls { MapScaleView() }
        .onAppear { fit() }
        .accessibilityIdentifier(identifier)
    }

    /// Рамка — порты (Каспий и Чёрное море: там паромы и шторма) и мои грузы, а не весь путь от Сианя:
    /// иначе морская часть коридора на телефоне мелкая.
    func fit() {
        let ports = snapshot.nodes.filter { $0.kind.known == .port }.map { GeoPoint(lat: $0.lat, lon: $0.lon) }
        let points = ports + mine.map { GeoPoint(lat: $0.position.lat, lon: $0.position.lon) }
        // поля шире: справа кнопки карты, по краям — подписи портов
        if !points.isEmpty { position = .rect(RouteMapView.rect(points, padding: 0.18)) }
    }
}

/// Закреплённая карта сверху «Коридора» с кнопками «Весь коридор» и «Развернуть».
struct CorridorMapHeader: View {
    let snapshot: MapSnapshot
    let mine: [Shipment]
    let onPort: (String) -> Void
    let onShipment: (String) -> Void
    @Environment(\.l10n) private var l
    @State private var expanded = false
    @State private var resetToken = 0

    var body: some View {
        CorridorMapView(snapshot: snapshot, mine: mine, onPort: onPort, onShipment: onShipment)
            .id(resetToken)  // «Весь коридор» — пересоздать карту с исходной рамкой
            .overlay(alignment: .topTrailing) {
                VStack(spacing: 8) {
                    mapButton("arrow.up.left.and.arrow.down.right", "corridor.expand", l("corridor.expand")) {
                        expanded = true
                    }
                    mapButton("scope", "corridor.fit", l("corridor.fit")) { resetToken += 1 }
                }
                .padding(10)
            }
            .sheet(isPresented: $expanded) {
                CorridorMapView(
                    snapshot: snapshot, mine: mine, identifier: "corridor.mapFull",
                    onPort: { code in expanded = false; onPort(code) },
                    onShipment: { ref in expanded = false; onShipment(ref) }
                )
                .overlay(alignment: .topTrailing) {
                    mapButton("xmark", "corridor.close", l("map.close")) { expanded = false }.padding()
                }
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
            }
    }

    private func mapButton(_ icon: String, _ id: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon).font(.subheadline.weight(.semibold)).padding(10)
        }
        .background(.regularMaterial, in: Circle())
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }
}
