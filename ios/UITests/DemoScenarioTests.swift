import XCTest

/// Сценарий демо для записи видео (`ios/scripts/record_demo.sh`): история груза MC-26-0398
/// от ссылки до доставки. Время переводит сам тест через `/api/v1/demo/clock`, поэтому пульт
/// в кадр не попадает. Нужен бэкенд `MOCK_DATA=true DEMO_CONTROL=true` на :8000; в обычном
/// прогоне UI-тестов сценарий пропускается.
final class DemoScenarioTests: XCTestCase {
    private static let server = URL(string: "http://localhost:8000")!

    override func setUpWithError() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["MC_DEMO_VIDEO"] == "1", "только для записи видео (MC_DEMO_VIDEO=1)")
        continueAfterFailure = false
    }

    @discardableResult
    private static func clock(_ action: String) async throws -> [String: Any] {
        var request = URLRequest(url: server.appending(path: "api/v1/demo/clock"), timeoutInterval: 10)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(#"{"action":"\#(action)"}"#.utf8)
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, "бэкенд без DEMO_CONTROL?")
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    private static func state() async throws -> String {
        let (data, _) = try await URLSession.shared.data(from: server.appending(path: "api/v1/shipments/MC-26-0398"))
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return json?["state"] as? String ?? ""
    }

    @MainActor private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.descendants(matching: .any)[id].firstMatch
    }

    @MainActor private func pause(_ seconds: Double) {
        Thread.sleep(forTimeInterval: seconds)
    }

    /// Обновить карточку жестом, как пользователь.
    /// Обновить жестом, как пользователь. Тянем сам экран: `collectionViews.firstMatch` мог бы
    /// попасть в скрытый список соседней вкладки TabView.
    /// (`swipeDown` слишком резкий: индикатор появляется, но порог обновления не пройден.)
    @MainActor private func pullToRefresh(_ app: XCUIApplication) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))  // ниже баннера уведомления
        start.press(forDuration: 0.1, thenDragTo: start.withOffset(CGVector(dx: 0, dy: 420)))
        pause(3)
    }

    @MainActor private func allowNotificationsIfAsked() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for label in ["Allow", "Разрешить"] where springboard.buttons[label].waitForExistence(timeout: 3) {
            springboard.buttons[label].tap()
            return
        }
    }

    @MainActor
    func test_story() async throws {
        try await Self.clock("reset")
        let app = XCUIApplication()
        app.launchArguments = ["-mc.lang", "ru", "-mc.demo", "NO"]
        app.launch()

        // 1. Списка нет — видно состояние коридора
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 20))
        pause(4)
        app.tabBars.buttons["tab.corridor"].tap()
        pause(4)
        app.tabBars.buttons["tab.shipments"].tap()
        pause(1)

        // 2. Ссылка от оператора → груз: маршрут, где сейчас, ETA
        app.open(URL(string: "mcstatus://s/MC-26-0398")!)
        allowNotificationsIfAsked()
        XCTAssertTrue(app.navigationBars["MC-26-0398"].waitForExistence(timeout: 10))
        pause(4)
        app.swipeUp()
        pause(3)

        // 3. На экран блокировки
        let live = el(app, "card.liveActivity")
        for _ in 0..<4 where !live.exists { app.swipeUp() }
        if live.exists, live.label.contains("На экран") { live.tap() }
        pause(2)
        for _ in 0..<5 { app.swipeDown() }

        // 4–5. Шторм в Актау: уведомление, запрет, очередь «2–3 дня, до 5»
        try await Self.clock("next_beat")
        pullToRefresh(app)
        pause(4)
        app.swipeUp()
        pause(4)
        XCUIDevice.shared.press(.home)
        pause(5)  // Dynamic Island и уведомления
        app.activate()
        pause(2)

        // 7. Перемотка: погружен на паром, вышел, … доставлен — Live Activity закрывается
        for _ in 0..<5 { app.swipeDown() }
        try await Self.clock("next_beat")
        pullToRefresh(app)
        pause(4)
        for _ in 0..<14 {
            if try await Self.state() == "delivered" { break }
            try await Self.clock("next_beat")
            pullToRefresh(app)
            pause(1)
        }
        let final = try await Self.state()
        XCTAssertEqual(final, "delivered")
        pullToRefresh(app)
        pause(4)
        XCUIDevice.shared.press(.home)
        pause(4)
    }
}
