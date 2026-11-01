#!/bin/bash
# Видео демо с симулятора: сценарий ведёт DemoScenarioTests, время переводит тест.
# Нужен бэкенд из корня репозитория: MOCK_DATA=true DEMO_CONTROL=true .venv/bin/python -m app.main
# Запуск: ios/scripts/record_demo.sh [ios/build/demo.mp4]
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
DEVICE="${DEVICE:-iPhone 17}"
OUT="${1:-build/demo.mp4}"
DEST="platform=iOS Simulator,name=$DEVICE"

curl -sf localhost:8000/api/v1/demo/clock >/dev/null || {
  echo "Нет бэкенда с DEMO_CONTROL на :8000 — запустите его (см. ios/README.md)." >&2
  exit 1
}
mkdir -p "$(dirname "$OUT")"
xcrun simctl boot "$DEVICE" 2>/dev/null || true
xcrun simctl uninstall booted com.malakhouski.mcstatus 2>/dev/null || true  # с пустого списка
xcodegen generate >/dev/null
xcodebuild build-for-testing -scheme MiddleCorridor -destination "$DEST" -quiet

xcrun simctl io booted recordVideo --codec h264 --force "$OUT" &
REC=$!
sleep 2
STATUS=0
TEST_RUNNER_MC_DEMO_VIDEO=1 xcodebuild test-without-building -scheme MiddleCorridor -destination "$DEST" \
  -only-testing:MiddleCorridorUITests/DemoScenarioTests -quiet || STATUS=$?
sleep 1
kill -INT "$REC" 2>/dev/null || true
wait "$REC" 2>/dev/null || true
SHORT="${OUT%.mp4}.720p.mp4"
swift scripts/compress_video.swift "$OUT" "$SHORT" || true  # 720p — для пересылки
echo "Видео: $OUT, короткое: $SHORT (сценарий: exit $STATUS)"
exit "$STATUS"
