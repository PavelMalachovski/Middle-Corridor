# Middle Corridor — iOS

Нативное приложение (SwiftUI, iOS 17+) поверх того же `/api/v1`, что и веб-карта.
Видение и решения — [`docs/IOS.md`](../docs/IOS.md).

```
ios/
  project.yml   проект Xcode (XcodeGen); .xcodeproj генерируется, в git его нет
  MCCore/       Swift Package без UI: модели /api/v1, клиент, разбор ссылок,
                подписи RU/EN, «Мои грузы»; тесты — swift test, без симулятора
  App/          SwiftUI-экраны поверх MCCore
  UITests/      смоук-тесты экранов на фейковом API (-mc-fake-api)
```

## Один раз на Маке

```bash
brew install xcodegen python@3.11
```

Если `xcode-select -p` показывает `/Library/Developer/CommandLineTools`, то
`xcodebuild`/`simctl` не найдутся. Нужно либо `sudo xcode-select -s /Applications/Xcode.app`,
либо `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` в сессии.

## Каждый день

```bash
cd ios && xcodegen generate                 # после pull и правок project.yml
cd ios/MCCore && swift test                 # логика, ~секунды
cd ios && xcodebuild -scheme MiddleCorridor -destination 'platform=iOS Simulator,name=iPhone 17' build
cd ios && xcodebuild test -scheme MiddleCorridor -destination 'platform=iOS Simulator,name=iPhone 17' -resultBundlePath build/ui.xcresult
xcrun xcresulttool export attachments --path build/ui.xcresult --output-path build/shots   # скриншоты смоука
open ios/MiddleCorridor.xcodeproj           # или Xcode → Run
```

## Бэкенд для демо

Из корня репозитория, синтетика без Postgres и ключей:

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
MOCK_DATA=true .venv/bin/python -m app.main     # слушает 0.0.0.0:8000
```

Симулятор ходит на `http://localhost:8000` (по умолчанию). iPhone — на IP Мака
в той же Wi‑Fi: `ipconfig getifaddr en0`, адрес вводится в «Настройках» приложения,
на запрос «Локальная сеть» ответить «Разрешить».

## Запуск на iPhone

iPhone по кабелю → Xcode → таргет MiddleCorridor → Signing & Capabilities →
Team: Personal Team (бесплатный Apple ID) → Run. На телефоне: Настройки → Основные →
VPN и управление устройством → доверять разработчику. Сборка с Personal Team живёт 7 дней.

## Ссылки

- `mcstatus://s/MC-26-0412` — открыть груз (проверка: `xcrun simctl openurl booted "mcstatus://s/MC-26-0412"`;
  система спросит «Open in…?», в UI-тестах вместо этого `app.open(url)`).
- `https://<домен>/?s=MC-26-0412` — Universal Link; нужен платный Apple Developer (Associated Domains).
