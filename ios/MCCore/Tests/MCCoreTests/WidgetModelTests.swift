import XCTest
@testable import MCCore

final class WidgetModelTests: XCTestCase {
    func test_resolve_prefersIntent() {
        XCTAssertEqual(
            WidgetModel.resolve(intentRef: " mc-26-0412 ", sharedRef: "MC-26-0398", cachedRefs: ["MC-26-0322"]),
            "MC-26-0412")
    }

    func test_resolve_fallsBackToShared() {
        XCTAssertEqual(
            WidgetModel.resolve(intentRef: "  ", sharedRef: "MC-26-0398", cachedRefs: ["MC-26-0322"]), "MC-26-0398")
    }

    func test_resolve_garbageIntent_usesShared() {
        XCTAssertEqual(WidgetModel.resolve(intentRef: "привет", sharedRef: "MC-26-0398", cachedRefs: []), "MC-26-0398")
    }

    func test_resolve_cache() {
        XCTAssertEqual(WidgetModel.resolve(intentRef: nil, sharedRef: nil, cachedRefs: ["MC-26-0322", "MC-26-0398"]), "MC-26-0322")
    }

    func test_resolve_none_isNil() {
        XCTAssertNil(WidgetModel.resolve(intentRef: nil, sharedRef: nil, cachedRefs: []))
    }

    func test_placeholderTexts() {
        let ru = Labels(lang: .ru, nodes: [])
        XCTAssertEqual(ru.text("widget.choose"), "Выберите груз в настройках виджета")
        XCTAssertEqual(Labels(lang: .en, nodes: []).text("widget.offline"), "No connection to the server")
    }
}
