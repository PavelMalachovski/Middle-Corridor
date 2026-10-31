"""Дополняет фикстуры MCCore полями недели 2, не меняя существующих значений.

Фикстуры сняты с мок-бэкенда 31.10.2026 (forecast и thresholds в них уже
есть); прогноз очереди появился позже — добавляем его у MC-26-0398 так, как
его отдаёт мок без демо-истории: Актау, 4 места, 8 в сутки, 48 ч погоды.
Запуск: python3 ios/scripts/patch_fixtures.py (идемпотентно).
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "MCCore/Tests/MCCoreTests/Fixtures"
QUEUE = {
    "port_code": "AKTAU",
    "position": 4,
    "per_day": 8.0,
    "weather_hours": 48.0,
    "p50_hours": 60.0,
    "p90_hours": 120.0,
    "basis_code": "weather_ban",
}


def _with_queue(shipment: dict) -> dict:
    if shipment.get("ref") == "MC-26-0398":
        shipment["queue"] = QUEUE
    return shipment


def main() -> None:
    snapshot_path = FIXTURES / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["shipments"] = [_with_queue(s) for s in snapshot["shipments"]]
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")

    path = FIXTURES / "shipment_MC-26-0398.json"
    path.write_text(
        json.dumps(_with_queue(json.loads(path.read_text())), ensure_ascii=False, indent=1) + "\n"
    )


if __name__ == "__main__":
    main()
