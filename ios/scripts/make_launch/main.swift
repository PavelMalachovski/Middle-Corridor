// Картинка экрана запуска (UILaunchScreen → UIImageName: LaunchEmblem) из того же SwiftUI-кода,
// что рисует заставку, — первый кадр анимации совпадает с экраном запуска. Запуск из корня:
//   DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swiftc -O ios/App/Splash/CaspianEmblem.swift \
//     ios/scripts/make_launch/main.swift -o /tmp/make_launch && /tmp/make_launch ios/App/Assets.xcassets/LaunchEmblem.imageset
import AppKit
import SwiftUI

/// Экран запуска показывает числа картинки и цвета `LaunchBackground` как Display P3, без учёта
/// профиля (проверено по кадрам видео: sRGB #072A24 выходил #012B24). Поэтому и картинка, и фон —
/// в P3 с пересчитанными значениями: цвет совпадает с заставкой при любой трактовке.
func displayP3(_ image: CGImage) -> CGImage? {
    guard let space = CGColorSpace(name: CGColorSpace.displayP3),
        let context = CGContext(
            data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: 0,
            space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return nil }
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return context.makeImage()
}

@MainActor
func render(to directory: URL) throws {
    for scale in [2, 3] {
        let renderer = ImageRenderer(content: CaspianEmblem())
        renderer.scale = CGFloat(scale)
        guard let image = renderer.cgImage.flatMap(displayP3),
            let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
        else { throw CocoaError(.fileWriteUnknown) }
        let url = directory.appending(path: "LaunchEmblem@\(scale)x.png")
        try png.write(to: url)
        print("\(image.width)×\(image.height) → \(url.path)")
    }
}

let out = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? ".")
try MainActor.assumeIsolated { try render(to: out) }
