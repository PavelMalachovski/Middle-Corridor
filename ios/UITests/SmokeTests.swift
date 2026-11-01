import XCTest

/// Смоук экранов на вшитых данных мок-бэкенда (`-mc-fake-api`), без сервера.
/// Каждый тест оставляет скриншот в .xcresult — смотреть глазами после правок UI.
final class SmokeTests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    @MainActor
    private func launch(lang: String = "ru") -> XCUIApplication {
        let app = XCUIApplication()
        // -mc.demo NO: пульт выключен при каждом запуске (UserDefaults симулятора живут между тестами)
        app.launchArguments = ["-mc-fake-api", "-mc.lang", lang, "-mc.demo", "NO"]
        app.launch()
        return app
    }

    @MainActor
    private func shot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    @MainActor
    private func element(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.descendants(matching: .any)[id].firstMatch
    }

    @MainActor
    private func add(_ app: XCUIApplication, _ text: String) {
        app.buttons["empty.add"].tap()
        let field = app.textFields["add.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText(text)
        app.buttons["add.submit"].tap()
    }

    @MainActor
    func test_emptyState_showsCorridorAndAdd() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        XCTAssertTrue(element(app, "corridor.title").waitForExistence(timeout: 5))
        shot(app, "01-empty-ru")
    }

    @MainActor
    func test_addByNumber_opensCard() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "mc-26-0412")
        XCTAssertTrue(app.navigationBars["MC-26-0412"].waitForExistence(timeout: 5))
        let position = element(app, "card.position")
        XCTAssertTrue(position.waitForExistence(timeout: 5))
        XCTAssertTrue(position.label.contains("Barda"), position.label)
        shot(app, "02-card-ru")

        app.navigationBars["MC-26-0412"].buttons.firstMatch.tap()
        XCTAssertTrue(element(app, "row.MC-26-0412").waitForExistence(timeout: 5))
        shot(app, "03-list-ru")
    }

    @MainActor
    func test_addUnknown_showsError() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "MC-00-0000")
        let error = element(app, "add.error")
        XCTAssertTrue(error.waitForExistence(timeout: 5))
        XCTAssertEqual(error.label, "Груз не найден")
        XCTAssertEqual(app.textFields["add.field"].value as? String, "MC-00-0000")
        shot(app, "04-add-error-ru")
    }

    @MainActor
    func test_deepLink() throws {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        app.open(try XCTUnwrap(URL(string: "mcstatus://s/MC-26-0398")))
        XCTAssertTrue(app.navigationBars["MC-26-0398"].waitForExistence(timeout: 10))
        let hold = element(app, "hold")
        XCTAssertTrue(hold.waitForExistence(timeout: 5))
        XCTAssertTrue(hold.label.contains("Погодный запрет"), hold.label)
        XCTAssertTrue(element(app, "card.map").exists)
        shot(app, "05-deeplink-hold-ru")

        let queue = element(app, "card.queue")
        app.swipeUp()
        XCTAssertTrue(queue.waitForExistence(timeout: 5))
        XCTAssertTrue(queue.label.contains("2–3 дня"), queue.label)
        let weather = element(app, "card.weather")
        if !weather.exists { app.swipeUp() }
        XCTAssertTrue(weather.waitForExistence(timeout: 5))
        XCTAssertTrue(weather.label.contains("Актау"), weather.label)
        shot(app, "09-card-weather-ru")
    }

    @MainActor
    func test_english() {
        let app = launch(lang: "en")
        XCTAssertTrue(app.navigationBars["My shipments"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["empty.add"].label, "Add shipment")
        add(app, "MC-26-0412")
        let event = element(app, "card.event")
        XCTAssertTrue(event.waitForExistence(timeout: 5))
        XCTAssertTrue(event.label.contains("loaded onto ferry"), event.label)
        shot(app, "06-card-en")
    }

    @MainActor
    func test_corridorTab() {
        let app = launch()
        let tab = app.tabBars.buttons["tab.corridor"]
        XCTAssertTrue(tab.waitForExistence(timeout: 5))
        tab.tap()
        let aktau = element(app, "port.AKTAU")
        XCTAssertTrue(aktau.waitForExistence(timeout: 5))
        XCTAssertTrue(element(app, "corridor.news").exists)
        shot(app, "07-corridor-ru")
        aktau.tap()
        XCTAssertTrue(element(app, "wind.chart").waitForExistence(timeout: 5))
        shot(app, "08-port-ru")
    }

    @MainActor
    func test_demoPanel() {
        let app = launch()
        XCTAssertTrue(app.buttons["settings"].waitForExistence(timeout: 5))
        app.buttons["settings"].tap()
        let version = element(app, "settings.version")
        if !version.waitForExistence(timeout: 3) { app.swipeUp() }  // строка версии — внизу формы
        XCTAssertTrue(version.waitForExistence(timeout: 5))
        XCTAssertFalse(element(app, "demo.section").exists)
        version.press(forDuration: 1.2)
        let section = element(app, "demo.section")
        if !section.waitForExistence(timeout: 5) { app.swipeDown() }
        XCTAssertTrue(section.waitForExistence(timeout: 5))
        let advance = element(app, "demo.advance24")
        if !advance.waitForExistence(timeout: 2) { app.swipeUp() }  // пульт — под секцией уведомлений
        XCTAssertTrue(advance.waitForExistence(timeout: 5))
        advance.tap()
        let offset = element(app, "demo.offset")
        XCTAssertTrue(offset.waitForExistence(timeout: 5))
        let shifted = NSPredicate(format: "label CONTAINS %@", "24")
        expectation(for: shifted, evaluatedWith: offset)
        waitForExpectations(timeout: 5)
        shot(app, "10-demo-ru")
    }

    @MainActor
    func test_notificationSettings() {
        let app = launch()
        XCTAssertTrue(app.buttons["settings"].waitForExistence(timeout: 5))
        app.buttons["settings"].tap()
        let storm = app.switches["notify.storm"]
        if !storm.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(storm.waitForExistence(timeout: 5))
        for id in ["notify.storm", "notify.event", "notify.delay", "notify.queue"] {
            let toggle = app.switches[id]
            XCTAssertTrue(toggle.exists, id)
            XCTAssertEqual(toggle.value as? String, "1", id)
        }
        shot(app, "11-settings-notify-ru")
    }

    @MainActor
    func test_liveActivity() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "MC-26-0412")
        XCTAssertTrue(app.navigationBars["MC-26-0412"].waitForExistence(timeout: 5))
        let button = element(app, "card.liveActivity")
        for _ in 0..<4 where !button.exists { app.swipeUp() }
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        if button.label.contains("Убрать") { button.tap() }  // осталась с прошлого запуска
        XCTAssertTrue(button.label.contains("На экран блокировки"), button.label)
        button.tap()
        let started = NSPredicate(format: "label CONTAINS %@", "Убрать с экрана блокировки")
        expectation(for: started, evaluatedWith: button)
        waitForExpectations(timeout: 5)
        shot(app, "12-live-activity-ru")

        XCUIDevice.shared.press(.home)
        sleep(2)
        let home = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        home.name = "13-dynamic-island"
        home.lifetime = .keepAlways
        add(home)

        app.activate()
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        button.tap()  // убрать за собой
    }

    @MainActor
    func test_demoPreview() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "MC-26-0398")
        XCTAssertTrue(app.navigationBars["MC-26-0398"].waitForExistence(timeout: 5))
        app.navigationBars["MC-26-0398"].buttons.firstMatch.tap()
        app.buttons["settings"].tap()
        let version = element(app, "settings.version")
        for _ in 0..<3 where !version.exists { app.swipeUp() }
        version.press(forDuration: 1.2)
        let preview = element(app, "demo.preview")
        for _ in 0..<3 where !preview.exists { app.swipeUp() }
        XCTAssertTrue(preview.waitForExistence(timeout: 5))
        preview.tap()
        XCTAssertTrue(element(app, "preview.live").waitForExistence(timeout: 5))
        XCTAssertTrue(element(app, "preview.widget").exists)
        shot(app, "14-preview-ru")
    }
}
