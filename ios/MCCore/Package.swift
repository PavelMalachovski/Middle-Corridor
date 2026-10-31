// swift-tools-version: 6.0
import PackageDescription

// Логика приложения без UI: модели /api/v1, клиент, разбор ссылок, подписи RU/EN,
// хранилище «Моих грузов». macOS — чтобы `swift test` шёл без симулятора.
let package = Package(
    name: "MCCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "MCCore", targets: ["MCCore"])],
    targets: [
        .target(name: "MCCore"),
        .testTarget(
            name: "MCCoreTests",
            dependencies: ["MCCore"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
