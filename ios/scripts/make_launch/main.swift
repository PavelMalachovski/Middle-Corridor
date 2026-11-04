// Картинка экрана запуска (UILaunchScreen → UIImageName: LaunchEmblem) из того же SwiftUI-кода,
// что рисует заставку, — первый кадр анимации совпадает с экраном запуска. Запуск из корня:
//   DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swiftc -O ios/App/Splash/CaspianEmblem.swift \
//     ios/scripts/make_launch/main.swift -o /tmp/make_launch && /tmp/make_launch ios/App/Assets.xcassets/LaunchEmblem.imageset
import AppKit
import SwiftUI

@MainActor
func render(to directory: URL) throws {
    for scale in [2, 3] {
        let renderer = ImageRenderer(content: CaspianEmblem())
        renderer.scale = CGFloat(scale)
        guard let image = renderer.cgImage,
            let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
        else { throw CocoaError(.fileWriteUnknown) }
        let url = directory.appending(path: "LaunchEmblem@\(scale)x.png")
        try png.write(to: url)
        print("\(image.width)×\(image.height) → \(url.path)")
    }
}

let out = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? ".")
try MainActor.assumeIsolated { try render(to: out) }
