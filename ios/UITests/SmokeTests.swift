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
        XCTAssertTrue(app.staticTexts["Коридор сейчас"].waitForExistence(timeout: 5))
        shot(app, "01-empty-ru")
    }

    @MainActor
    func test_addByNumber_opensCard() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "mc-26-0412")
        XCTAssertTrue(app.navigationBars["MC-26-0412"].waitForExistence(timeout: 5))
        let ferry = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Barda'")).firstMatch
        XCTAssertTrue(ferry.waitForExistence(timeout: 5))
        shot(app, "02-card-ru")

        app.navigationBars["MC-26-0412"].buttons.firstMatch.tap()
        XCTAssertTrue(app.buttons["row.MC-26-0412"].waitForExistence(timeout: 5))
        shot(app, "03-list-ru")
    }

    @MainActor
    func test_addUnknown_showsError() {
        let app = launch()
        XCTAssertTrue(app.buttons["empty.add"].waitForExistence(timeout: 5))
        add(app, "MC-00-0000")
        let error = app.staticTexts["add.error"]
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
        let hold = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Погодный запрет'")).firstMatch
        XCTAssertTrue(hold.waitForExistence(timeout: 5))
        shot(app, "05-deeplink-hold-ru")
    }

    @MainActor
    func test_english() {
        let app = launch(lang: "en")
        XCTAssertTrue(app.navigationBars["My shipments"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["empty.add"].label, "Add shipment")
        add(app, "MC-26-0412")
        let event = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'loaded onto ferry'")).firstMatch
        XCTAssertTrue(event.waitForExistence(timeout: 5))
        shot(app, "06-card-en")
    }
}
