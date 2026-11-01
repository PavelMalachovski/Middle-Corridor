// Иконка приложения 1024×1024: маршрут коридора на тёмно-бирюзовом фоне.
// Запуск: swift ios/scripts/make_icon.swift <путь.png>
// Пройденное — сплошной мятной линией, впереди — пунктиром, белая точка — «где сейчас»
// (как на карте в карточке груза).
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

let size = 1024
let out = CommandLine.arguments.dropFirst().first ?? "icon-1024.png"
let space = CGColorSpace(name: CGColorSpace.sRGB)!
guard let ctx = CGContext(
    data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0, space: space,
    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
else { fatalError("no context") }

func rgb(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
}

// фон: вертикальный градиент
let gradient = CGGradient(colorsSpace: space, colors: [rgb(0x0F5446), rgb(0x072A24)] as CFArray, locations: [0, 1])!
ctx.drawLinearGradient(gradient, start: CGPoint(x: 0, y: CGFloat(size)), end: .zero, options: [])

// «море» — мягкая полоса по диагонали
ctx.setFillColor(rgb(0x1B7F8C, 0.28))
ctx.fillEllipse(in: CGRect(x: 360, y: 300, width: 300, height: 420))

let route: [CGPoint] = [
    CGPoint(x: 150, y: 250), CGPoint(x: 300, y: 380), CGPoint(x: 420, y: 340),
    CGPoint(x: 540, y: 520), CGPoint(x: 700, y: 600), CGPoint(x: 800, y: 760), CGPoint(x: 880, y: 820),
]
let here = 3

func path(_ points: ArraySlice<CGPoint>) -> CGPath {
    let p = CGMutablePath()
    p.addLines(between: Array(points))
    return p
}

ctx.setLineCap(.round)
ctx.setLineJoin(.round)
// пройдено
ctx.setStrokeColor(rgb(0x2FD39A))
ctx.setLineWidth(46)
ctx.addPath(path(route[...here]))
ctx.strokePath()
// впереди — пунктир
ctx.setStrokeColor(rgb(0x2FD39A, 0.55))
ctx.setLineWidth(30)
ctx.setLineDash(phase: 0, lengths: [44, 40])
ctx.addPath(path(route[here...]))
ctx.strokePath()
ctx.setLineDash(phase: 0, lengths: [])

// узлы
ctx.setFillColor(rgb(0x2FD39A))
for (i, point) in route.enumerated() where i != here && (i == 0 || i == route.count - 1) {
    ctx.fillEllipse(in: CGRect(x: point.x - 40, y: point.y - 40, width: 80, height: 80))
}
// «где сейчас»: свечение, мятное кольцо, белая точка
let p = route[here]
ctx.setFillColor(rgb(0x2FD39A, 0.25))
ctx.fillEllipse(in: CGRect(x: p.x - 120, y: p.y - 120, width: 240, height: 240))
ctx.setFillColor(rgb(0x2FD39A))
ctx.fillEllipse(in: CGRect(x: p.x - 78, y: p.y - 78, width: 156, height: 156))
ctx.setFillColor(rgb(0xFFFFFF))
ctx.fillEllipse(in: CGRect(x: p.x - 50, y: p.y - 50, width: 100, height: 100))

guard let image = ctx.makeImage(),
    let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, UTType.png.identifier as CFString, 1, nil)
else { fatalError("no image") }
CGImageDestinationAddImage(dest, image, nil)
guard CGImageDestinationFinalize(dest) else { fatalError("write failed") }
print("icon → \(out)")
