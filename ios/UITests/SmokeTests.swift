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
        app.launchArguments = ["-mc-fake-api", "-mc.lang", lang]
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
        shot(app, "05-deeplink-hold-ru")
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
}
