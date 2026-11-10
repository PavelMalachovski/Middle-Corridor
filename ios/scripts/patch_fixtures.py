"""Дополняет фикстуры MCCore полями недели 2, не меняя существующих значений.

Фикстуры сняты с мок-бэкенда 31.10.2026 (forecast и thresholds в них уже
есть); прогноз очереди появился позже — добавляем его у MC-26-0398 так, как
его отдаёт мок без демо-истории: Актау, 4 места, 8 в сутки, 48 ч погоды.
Запуск: .venv/bin/python ios/scripts/patch_fixtures.py (идемпотентно; нужен пакет app).
Проверка санкций (04.11.2026): блок `sanctions` у каждого груза и груз MC-26-0431
(«возможна санкционка») в снимке — проекция мока на момент server_time снимка.
Сегменты коридора (неделя 5) взяты целиком из app.services.map_snapshot.static_segments().
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
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


# вилка ETA и разбор задержки (неделя 5): +18 ч — погодный запрет в Актау; вилка — P90−P50 очереди
DELAY_BREAKDOWN = [{"code": "weather_ban", "node_code": "AKTAU", "hours": 18.0}]
SPREAD_H = 60


def _with_queue(shipment: dict) -> dict:
    if shipment.get("ref") == "MC-26-0398":
        shipment["queue"] = QUEUE
        shipment["delay_breakdown"] = DELAY_BREAKDOWN
        if shipment.get("eta"):
            eta = datetime.fromisoformat(shipment["eta"].replace("Z", "+00:00"))
            latest = eta + timedelta(hours=SPREAD_H)
            shipment["eta_latest"] = latest.strftime("%Y-%m-%dT%H:%M:%SZ")
    return shipment


def _mock_shipments(at: datetime) -> dict[str, dict]:
    """Грузы мока на момент снимка — JSON, как их отдаёт /api/v1."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.integrations.mock.fleet import MockShipmentSource
    from app.services.tracking import project_shipment

    plans = asyncio.run(MockShipmentSource(lambda: at).list_plans(at))
    return {p.ref: project_shipment(p, at).model_dump(mode="json") for p in plans}


def _with_sanctions(shipment: dict, mock: dict[str, dict]) -> dict:
    shipment["sanctions"] = mock[shipment["ref"]]["sanctions"]
    shipment["cargo_details"] = mock[shipment["ref"]]["cargo_details"]  # блок «Груз»
    return shipment


def main() -> None:
    snapshot_path = FIXTURES / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    at = datetime.fromisoformat(snapshot["server_time"].replace("Z", "+00:00"))
    mock = _mock_shipments(at)
    shipments = [_with_sanctions(_with_queue(s), mock) for s in snapshot["shipments"]]
    if not any(s["ref"] == "MC-26-0431" for s in shipments):
        shipments.append(mock["MC-26-0431"])  # «возможна санкционка» для UI-смоука
    if not any(s["ref"] == "MC-26-0501" for s in shipments):
        shipments.append(mock["MC-26-0501"])  # восток, блок «Груз» с опасным грузом
    snapshot["shipments"] = shipments
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")

    for ref in ("MC-26-0398", "MC-26-0412"):
        path = FIXTURES / f"shipment_{ref}.json"
        shipment = _with_sanctions(_with_queue(json.loads(path.read_text())), mock)
        path.write_text(json.dumps(shipment, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
