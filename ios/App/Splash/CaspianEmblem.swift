import SwiftUI

// Эмблема «Каспий» для экрана запуска и заставки: море, точки переправы, порты Актау и Алят —
// без рельсов и парома (их дорисовывает SplashView). Геометрия и цвета — как в иконке
// (ios/scripts/make_icon.swift). Файл без UIKit и MCCore: из него же на macOS рендерится
// картинка экрана запуска — ios/scripts/make_launch/main.swift. Правка рисунка →
// перегенерировать LaunchEmblem, иначе первый кадр заставки «прыгнет».

/// Цвета иконки (вариант any) — sRGB-литералы: эмблема рисуется и под macOS.
enum EmblemColor {
    static let sea = Color(.sRGB, red: 0x1B / 255, green: 0x7F / 255, blue: 0x8C / 255)
    static let rail = Color(.sRGB, red: 0x2F / 255, green: 0xD3 / 255, blue: 0x9A / 255)
    static let ring = Color(.sRGB, red: 0xFA / 255, green: 0xB2 / 255, blue: 0x19 / 255)
    static let core = Color.white
    static let caption = Color(.sRGB, red: 0x9F / 255, green: 0xD9 / 255, blue: 0xC4 / 255)
}

struct CaspianEmblem: View {
    /// Размер в точках; картинка запуска — ровно такая, по центру экрана.
    static let size = CGSize(width: 208, height: 300)
    /// Единицы иконки (1024) → точки эмблемы: рамка — берег с отступом 20 по высоте.
    static let scale: CGFloat = 300 / 812
    /// Левый верхний угол эмблемы в единицах иконки: центр рамки — центр берега.
    private static let origin = CGPoint(x: 518.3 - 563 / 2, y: 531.9 - 812 / 2)

    // размеры — в единицах иконки, как в make_icon.swift
    static let railWidth: CGFloat = 42 * scale
    static let portRadius: CGFloat = 32 * scale
    static let ringRadius: CGFloat = 46 * scale
    static let coreRadius: CGFloat = 27 * scale
    private static let dotRadius: CGFloat = 12 * scale

    /// Порты в точках эмблемы (от её левого верхнего угла).
    static let aktau = point(lon: 51.2, lat: 43.65)
    static let alat = point(lon: 49.4, lat: 39.93)

    /// Точка переправы: 0 — Актау, 1 — Алят.
    static func crossing(_ t: CGFloat) -> CGPoint {
        CGPoint(x: aktau.x + (alat.x - aktau.x) * t, y: aktau.y + (alat.y - aktau.y) * t)
    }

    /// (долгота, широта) → точка: равнопромежуточная проекция иконки, сдвиг и масштаб эмблемы.
    static func point(lon: Double, lat: Double) -> CGPoint {
        let icon = CGPoint(x: 520 + (lon - 50.75) * 68, y: 530 - (lat - 41.95) * 76)
        return CGPoint(x: (icon.x - origin.x) * scale, y: (icon.y - origin.y) * scale)
    }

    /// Берег Каспия — упрощённый, точки те же, что в иконке.
    private static let coast: [(Double, Double)] = [
        (47.6, 45.7), (49.2, 46.5), (50.8, 46.95), (52.2, 47.0), (53.15, 46.5), (52.9, 45.6), (51.6, 45.25),
        (50.75, 44.75), (51.2, 44.2), (51.45, 43.4), (52.3, 42.6), (53.1, 42.0), (54.15, 41.85), (54.55, 41.2),
        (53.8, 40.75), (53.05, 40.55), (53.35, 39.5), (53.85, 38.3), (53.75, 37.35), (52.2, 36.85), (50.6, 37.05),
        (49.3, 37.55), (48.9, 38.5), (49.1, 39.5), (49.85, 40.25), (49.35, 40.75), (48.6, 41.7), (47.75, 42.75),
        (47.35, 43.6), (46.9, 44.5),
    ]

    /// Море: замкнутый сплайн Катмулла — Рома через точки берега.
    static let sea: Path = {
        let points = coast.map { point(lon: $0.0, lat: $0.1) }
        var path = Path()
        path.move(to: points[0])
        for i in points.indices {
            let p0 = points[(i - 1 + points.count) % points.count], p1 = points[i]
            let p2 = points[(i + 1) % points.count], p3 = points[(i + 2) % points.count]
            path.addCurve(
                to: p2,
                control1: CGPoint(x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6),
                control2: CGPoint(x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6))
        }
        path.closeSubpath()
        return path
    }()

    static func disc(_ center: CGPoint, _ radius: CGFloat) -> Path {
        Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2))
    }

    var body: some View {
        Canvas { context, _ in
            context.fill(Self.sea, with: .color(EmblemColor.sea))
            for t: CGFloat in [0.2, 0.3, 0.7, 0.8] {
                context.fill(Self.disc(Self.crossing(t), Self.dotRadius), with: .color(EmblemColor.core))
            }
            context.fill(Self.disc(Self.aktau, Self.portRadius), with: .color(EmblemColor.rail))
            context.fill(Self.disc(Self.alat, Self.portRadius), with: .color(EmblemColor.rail))
        }
        .frame(width: Self.size.width, height: Self.size.height)
    }
}
