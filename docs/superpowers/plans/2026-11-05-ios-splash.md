# iOS: заставка «Переправа» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** статичный экран запуска с эмблемой «Каспий» и анимированная заставка поверх приложения при холодном старте.

**Architecture:** чистая логика времени — в MCCore (`SplashTimeline`, тесты `swift test`); эмблема — кроссплатформенный SwiftUI-файл, из которого и приложение рисует заставку, и скрипт на macOS рендерит PNG экрана запуска; оверлей — в `RootView` по флагу `AppModel.showSplash`.

**Tech Stack:** Swift 6, SwiftUI (iOS 17+), XcodeGen, XCTest/XCUITest, `ImageRenderer` (macOS 14+).

**Spec:** `docs/superpowers/specs/2026-11-05-ios-splash-design.md`

## Global Constraints

- Подписи только английские: «Middle Corridor», «Aktau → Alat», через `Text(verbatim:)`.
- Цвета эмблемы — как у иконки (`make_icon.swift`, вариант any): море `#1B7F8C`, рельсы и порты `#2FD39A`, кольцо парома `#FAB219`, точки и ядро `#FFFFFF`; фон `#072A24`.
- Тайминг, с: рельсы 0–0,45; паром 0,35–1,15 (проявление 0,35–0,45); подпись 0,8–1,15; затухание 1,45–1,75; пропуск тапом — затухание 0,2.
- Все команды Xcode — с `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

## Review Focus

1. Открытие по `mcstatus://` при холодном старте — заставка уходит сразу, карточка груза видна (Task 3: `open(url)` сбрасывает `showSplash`; тест модели).
2. Тап по уведомлению/виджету (`show(ref)`) — то же (Task 3, тест модели).
3. Тап во время заставки — затухание за 0,2 с от текущей прозрачности, без скачка (Task 1: `frame(at:skippedAt:)`).
4. Время за пределами шкалы (отрицательное, после конца) — кадр зажат, не NaN (Task 1).
5. Маленький экран (iPhone SE, 375×667) — подпись не обрезается (Task 2: проверка глазами на скриншоте; эмблема 300 pt по высоте + подпись ≤ 560 pt).

---

### Task 1: SplashTimeline в MCCore

**Files:**
- Create: `ios/MCCore/Sources/MCCore/SplashTimeline.swift`
- Test: `ios/MCCore/Tests/MCCoreTests/SplashTimelineTests.swift`

**Interfaces:**
- Produces: `public struct SplashFrame: Equatable, Sendable { rails, ferry, ferryOpacity, wordmark, opacity: Double }`; `public enum SplashTimeline { static let duration = 1.75; static let skipFade = 0.2; static func frame(at t: Double, skippedAt: Double? = nil) -> SplashFrame; static func isFinished(at t: Double, skippedAt: Double?) -> Bool }`.

- [ ] Тесты: `t=0` → rails 0, ferry 0, ferryOpacity 0, wordmark 0, opacity 1; `t=0.45` → rails 1; `t=1.15` → ferry 1, wordmark 1; `t=1.45` → opacity 1; `t=1.75` → opacity 0 и `isFinished`; `t=-1` равен кадру `t=0`; `t=10` равен кадру `t=1.75`; пропуск: `frame(at: 0.5, skippedAt: 0.4).opacity ≈ 0.5`, `isFinished(at: 0.6, skippedAt: 0.4)`, в остальном кадр как без пропуска; ferry монотонно растёт на 0,35–1,15.
- [ ] Прогон — FAIL (нет типа).
- [ ] Реализация: линейный прогресс фазы `clamp((t - start)/(end - start))`, к рельсам — ease-out, к парому — ease-in-out (smoothstep); opacity = min(затухание шкалы, затухание пропуска).
- [ ] `swift test` — PASS. Коммит.

### Task 2: эмблема, экран запуска, скрипт рендера

**Files:**
- Create: `ios/App/Splash/CaspianEmblem.swift`, `ios/scripts/make_launch/main.swift`, `ios/App/Assets.xcassets/LaunchBackground.colorset/Contents.json`, `ios/App/Assets.xcassets/LaunchEmblem.imageset/{Contents.json,@1x/@2x/@3x png}`
- Modify: `ios/project.yml` (`UILaunchScreen`, `UIStatusBarHidden`)

**Interfaces:**
- Produces: `struct CaspianEmblem: View` (без UIKit/MCCore) с `static let size: CGSize` (высота 300 pt), `static func aktau(in origin: CGPoint) -> CGPoint`, `static func alat(in origin: CGPoint) -> CGPoint`, `static let scale: CGFloat`; рисует море, 4 точки переправы, 2 порта. Цвета — `enum EmblemColor { sea, rail, ring, core }`.
- [ ] Геометрия: берег и `xy(lon, lat)` — из `make_icon.swift`; рамка — bbox берега + 20 ед. отступа; масштаб = 300 / высота рамки.
- [ ] Скрипт: `swiftc -O ios/App/Splash/CaspianEmblem.swift ios/scripts/make_launch/main.swift -o <tmp> && <tmp> ios/App/Assets.xcassets/LaunchEmblem.imageset` → три PNG с альфой.
- [ ] `project.yml`: `UILaunchScreen: {UIColorName: LaunchBackground, UIImageName: LaunchEmblem}`, `UIStatusBarHidden: true`; `xcodegen generate`; сборка — `BUILD SUCCEEDED`. Коммит.

### Task 3: SplashView, флаг в AppModel, оверлей в RootView

**Files:**
- Create: `ios/App/Splash/SplashView.swift`
- Modify: `ios/App/AppModel.swift`, `ios/App/Views/RootView.swift`, `ios/UITests/SmokeTests.swift`

**Interfaces:**
- Consumes: `SplashTimeline`, `CaspianEmblem`.
- Produces: `AppModel.showSplash: Bool` (init: `defaults.object(forKey: "mc.splash") as? Bool ?? true`); `open(_:)` и `show(_:)` ставят `false`. `SplashView(onFinish: () -> Void)`, идентификатор доступности `splash`.
- [ ] `SplashView`: `TimelineView(.animation)` от `Date` старта; фон `Color("LaunchBackground")` `.ignoresSafeArea()`; эмблема по центру экрана (как картинка запуска); рельсы — `Path` от края экрана до порта, `.trim(from: 0, to: rails)`, ширина `42 * scale`, скругления как в иконке; паром — точка на отрезке Актау→Алят; подпись под эмблемой (28 pt semibold белым, 15 pt `#9FD9C4`, подъём 6 pt по `wordmark`); `.onTapGesture` → `skippedAt`; конец — `onFinish()`.
- [ ] `RootView`: `.overlay { if model.showSplash && !reduceMotion && !voiceOver { SplashView { model.showSplash = false }.transition(.opacity) } }`, `.animation(.easeOut(duration: 0.2), value: model.showSplash)`, `.statusBarHidden(model.showSplash)`; если заставку не показываем из-за доступности — `showSplash = false` в `onAppear`.
- [ ] UI-тесты: в `launch()` добавить `-mc.splash NO`; новый `test_splash_showsThenHands_overToShipments` — запуск без флага, `splash` существует, через ≤5 с исчезает, `empty.add` нажимаема; скриншот кадра середины.
- [ ] Сборка + `xcodebuild test` (смоук) — PASS; проверка глазами: запись видео запуска (`simctl io recordVideo`) — первый кадр заставки совпадает с экраном запуска. Коммит.

### Task 4: документация

- [ ] `ios/README.md` — команда перегенерации картинки запуска; `CLAUDE.md` — строка в «Грабли» (PNG экрана запуска рендерится из `CaspianEmblem`, перегенерировать после правки эмблемы; `-mc.splash NO` в UI-тестах); `docs/IOS.md` — строка в плане. Коммит, PR.
