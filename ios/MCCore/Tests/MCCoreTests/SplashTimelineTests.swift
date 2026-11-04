import XCTest
@testable import MCCore

final class SplashTimelineTests: XCTestCase {
    private let eps = 1e-9

    func test_start_onlyStaticFrame() {
        let f = SplashTimeline.frame(at: 0)
        XCTAssertEqual(f, SplashFrame(rails: 0, ferry: 0, ferryOpacity: 0, wordmark: 0, opacity: 1))
        XCTAssertFalse(SplashTimeline.isFinished(at: 0, skippedAt: nil))
    }

    func test_railsArriveFirst() {
        XCTAssertEqual(SplashTimeline.frame(at: 0.45).rails, 1, accuracy: eps)
        XCTAssertEqual(SplashTimeline.frame(at: 0.45).ferry, 0.125, accuracy: 0.1)  // паром только отошёл
        let half = SplashTimeline.frame(at: 0.225).rails
        XCTAssertGreaterThan(half, 0.5)  // ease-out: к середине — больше половины пути
        XCTAssertLessThan(half, 1)
    }

    func test_ferryCrossesThenWordmark() {
        XCTAssertEqual(SplashTimeline.frame(at: 0.35).ferryOpacity, 0, accuracy: eps)
        XCTAssertEqual(SplashTimeline.frame(at: 0.45).ferryOpacity, 1, accuracy: eps)
        XCTAssertEqual(SplashTimeline.frame(at: 0.8).wordmark, 0, accuracy: eps)
        let f = SplashTimeline.frame(at: 1.15)
        XCTAssertEqual(f.ferry, 1, accuracy: eps)
        XCTAssertEqual(f.wordmark, 1, accuracy: eps)
        XCTAssertEqual(f.opacity, 1, accuracy: eps)
    }

    func test_ferryMovesMonotonically() {
        var last = -1.0
        for step in 0...80 {
            let ferry = SplashTimeline.frame(at: 0.35 + Double(step) * 0.01).ferry
            XCTAssertGreaterThanOrEqual(ferry, last)
            last = ferry
        }
    }

    func test_holdThenFadeOut() {
        XCTAssertEqual(SplashTimeline.frame(at: 1.45).opacity, 1, accuracy: eps)
        XCTAssertEqual(SplashTimeline.frame(at: 1.6).opacity, 0.5, accuracy: eps)
        XCTAssertEqual(SplashTimeline.frame(at: SplashTimeline.duration).opacity, 0, accuracy: eps)
        XCTAssertFalse(SplashTimeline.isFinished(at: 1.7, skippedAt: nil))
        XCTAssertTrue(SplashTimeline.isFinished(at: 1.75, skippedAt: nil))
    }

    func test_outOfRange_isClamped() {
        XCTAssertEqual(SplashTimeline.frame(at: -1), SplashTimeline.frame(at: 0))
        XCTAssertEqual(SplashTimeline.frame(at: 10), SplashTimeline.frame(at: SplashTimeline.duration))
        XCTAssertEqual(SplashTimeline.frame(at: .infinity), SplashTimeline.frame(at: SplashTimeline.duration))
    }

    func test_tapSkip_fadesFromCurrentFrame() {
        let plain = SplashTimeline.frame(at: 0.5)
        let skipped = SplashTimeline.frame(at: 0.5, skippedAt: 0.4)
        XCTAssertEqual(skipped.opacity, 0.5, accuracy: eps)  // 0,1 с из 0,2 с затухания
        XCTAssertEqual(skipped.rails, plain.rails)
        XCTAssertEqual(skipped.ferry, plain.ferry)
        XCTAssertFalse(SplashTimeline.isFinished(at: 0.55, skippedAt: 0.4))
        XCTAssertTrue(SplashTimeline.isFinished(at: 0.6, skippedAt: 0.4))
    }

    func test_tapDuringFadeOut_neverBrightens() {
        // тап на середине обычного затухания: прозрачность не прыгает вверх
        XCTAssertEqual(SplashTimeline.frame(at: 1.61, skippedAt: 1.6).opacity, SplashTimeline.frame(at: 1.61).opacity, accuracy: 1e-6)
    }
}
