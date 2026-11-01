// Иконка приложения 1024×1024 «Каспий»: силуэт моря, рельсы с двух берегов (из Актау — на восток,
// из Алята — на запад), переправа точками, паром «где сейчас» — амберное кольцо. Прежняя иконка
// (восходящая ломаная с точками) читалась как график акций — см. docs/IOS-UX.md.
//
// Варианты для iOS 18+: any — на фирменном градиенте, без альфа-канала (так требует App Store);
// dark — без фона (его рисует система); tinted — оттенки серого без фона (тон добавляет система).
// Запуск (все три — в AppIcon.appiconset):
//   swift ios/scripts/make_icon.swift ios/App/Assets.xcassets/AppIcon.appiconset/icon-1024.png any
//   swift ios/scripts/make_icon.swift ios/App/Assets.xcassets/AppIcon.appiconset/icon-dark-1024.png dark
//   swift ios/scripts/make_icon.swift ios/App/Assets.xcassets/AppIcon.appiconset/icon-tinted-1024.png tinted
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

let size = 1024
let args = Array(CommandLine.arguments.dropFirst())
let out = args.first ?? "icon-1024.png"
let variant = args.count > 1 ? args[1] : "any"
guard ["any", "dark", "tinted"].contains(variant) else { fatalError("вариант: any | dark | tinted") }

let space = CGColorSpace(name: CGColorSpace.sRGB)!
let alpha: CGImageAlphaInfo = variant == "any" ? .noneSkipLast : .premultipliedLast
guard let ctx = CGContext(
    data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0, space: space,
    bitmapInfo: alpha.rawValue)
else { fatalError("no context") }

// координаты — как в SVG: начало сверху слева, y вниз
ctx.translateBy(x: 0, y: CGFloat(size))
ctx.scaleBy(x: 1, y: -1)

func rgb(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
}

// цвета — токены дизайн-системы: icon-ground-top/bottom, icon-sea, icon-route (мятный), watch (амбер)
let palette: (sea: UInt32, rail: UInt32, dots: UInt32, ring: UInt32, core: UInt32) =
    switch variant {
    case "dark": (0x1F8F9C, 0x2FD39A, 0xFFFFFF, 0xFAB219, 0xFFFFFF)
    case "tinted": (0x6B6B6B, 0xE6E6E6, 0xFFFFFF, 0xBDBDBD, 0xFFFFFF)
    default: (0x1B7F8C, 0x2FD39A, 0xFFFFFF, 0xFAB219, 0xFFFFFF)
    }

if variant == "any" {
    let gradient = CGGradient(colorsSpace: space, colors: [rgb(0x0F5446), rgb(0x072A24)] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(gradient, start: .zero, end: CGPoint(x: 0, y: CGFloat(size)), options: [])
} else {
    ctx.clear(CGRect(x: 0, y: 0, width: size, height: size))
}

/// (долгота, широта) → точка иконки: равнопромежуточная проекция с поправкой на широту Каспия.
func xy(_ lon: Double, _ lat: Double) -> CGPoint {
    CGPoint(x: 520 + (lon - 50.75) * 68, y: 530 - (lat - 41.95) * 76)
}

// берег Каспия — упрощённый: без мелких заливов, Мангышлак и Кара-Богаз мягкими выступами
let coast: [(Double, Double)] = [
    (47.6, 45.7), (49.2, 46.5), (50.8, 46.95), (52.2, 47.0), (53.15, 46.5), (52.9, 45.6), (51.6, 45.25),
    (50.75, 44.75), (51.2, 44.2), (51.45, 43.4), (52.3, 42.6), (53.1, 42.0), (54.15, 41.85), (54.55, 41.2),
    (53.8, 40.75), (53.05, 40.55), (53.35, 39.5), (53.85, 38.3), (53.75, 37.35), (52.2, 36.85), (50.6, 37.05),
    (49.3, 37.55), (48.9, 38.5), (49.1, 39.5), (49.85, 40.25), (49.35, 40.75), (48.6, 41.7), (47.75, 42.75),
    (47.35, 43.6), (46.9, 44.5),
]
let aktau = xy(51.2, 43.65)
let alat = xy(49.4, 39.93)

// море: замкнутый сплайн Катмулла — Рома через точки берега
let points = coast.map { xy($0.0, $0.1) }
let sea = CGMutablePath()
sea.move(to: points[0])
for i in 0..<points.count {
    let p0 = points[(i - 1 + points.count) % points.count], p1 = points[i]
    let p2 = points[(i + 1) % points.count], p3 = points[(i + 2) % points.count]
    let c1 = CGPoint(x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6)
    let c2 = CGPoint(x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6)
    sea.addCurve(to: p2, control1: c1, control2: c2)
}
sea.closeSubpath()
ctx.addPath(sea)
ctx.setFillColor(rgb(palette.sea))
ctx.fillPath()

// рельсы: из Актау на восток (Казахстан, Китай), из Алята на запад (Грузия, Европа)
ctx.setStrokeColor(rgb(palette.rail))
ctx.setLineWidth(42)
ctx.setLineCap(.round)
ctx.setLineJoin(.round)
let east = CGMutablePath()
east.move(to: CGPoint(x: 1024, y: aktau.y - 34))
east.addLine(to: CGPoint(x: aktau.x + 64, y: aktau.y - 34))
east.addQuadCurve(to: CGPoint(x: aktau.x, y: aktau.y + 4), control: CGPoint(x: aktau.x, y: aktau.y - 34))
let west = CGMutablePath()
west.move(to: CGPoint(x: alat.x, y: alat.y - 4))
west.addQuadCurve(to: CGPoint(x: alat.x - 64, y: alat.y + 36), control: CGPoint(x: alat.x, y: alat.y + 36))
west.addLine(to: CGPoint(x: 0, y: alat.y + 36))
ctx.addPath(east)
ctx.addPath(west)
ctx.strokePath()

func disc(_ ctx: CGContext, _ center: CGPoint, _ radius: CGFloat, _ color: UInt32) {
    ctx.setFillColor(rgb(color))
    ctx.fillEllipse(in: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2))
}

func along(_ t: CGFloat) -> CGPoint {
    CGPoint(x: aktau.x + (alat.x - aktau.x) * t, y: aktau.y + (alat.y - aktau.y) * t)
}

// переправа — точками, не задевая кружки портов и паром
for t in [0.2, 0.3, 0.7, 0.8] as [CGFloat] { disc(ctx, along(t), 12, palette.dots) }
disc(ctx, aktau, 32, palette.rail)
disc(ctx, alat, 32, palette.rail)
// паром «где сейчас» — посередине переправы
disc(ctx, along(0.5), 46, palette.ring)
disc(ctx, along(0.5), 27, palette.core)

guard let image = ctx.makeImage(),
    let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, UTType.png.identifier as CFString, 1, nil)
else { fatalError("no image") }
CGImageDestinationAddImage(dest, image, nil)
guard CGImageDestinationFinalize(dest) else { fatalError("write failed") }
print("icon (\(variant)) → \(out)")
