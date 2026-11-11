"""Снимает фикстуры MCCore с мок-бэкенда: снимок и карточки двух демо-грузов.

Демо — ровно два груза: MC-26-0501 (восток Млада-Болеслав → Костанай, блок «Груз»)
и MC-26-0431 (запад, «возможна санкционка»). Момент снимка — server_time из
существующего snapshot.json (31.10.2026), чтобы даты в тестах не плыли.

0501 снимается на такте «шторм» истории ведущего (story.py, T0 + 12 ч): ждёт в
Алята парома, погодный запрет на швартовку в Актау, очередь (p50 60 ч / p90 120 ч),
разбор задержки и вилка ETA — всё, что раньше давал вручную дописанный 0398.
Ветер Актау при этом критический (история гонит его так же, как на демо).
Отдельная карточка shipment_MC-26-0501_ferry.json — публичный 0501 без истории в
середине рейса «Shahdag» (позиция по AIS парома, «погружен на паром»).
Снимок собирается целиком (узлы, суда, сегменты, новости, сводки) тем же
MapSnapshotService, что и /api/v1/snapshot; пульта демо (`demo`) в нём нет.

Запуск: .venv/bin/python ios/scripts/patch_fixtures.py (идемпотентно; нужен пакет app).
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "ios/MCCore/Tests/MCCoreTests/Fixtures"
REFS = ("MC-26-0501", "MC-26-0431")
STORM_AFTER_H = 12  # такт «шторм» истории: STORM_START_H + STORM_BEAT_LAG_H
FERRY_AFTER_H = 14  # публичный 0501 через 14 ч после отхода «Shahdag» из Алята (рейс 20 ч)


def _snapshot(at: datetime, live: dict, *, story: bool = True) -> dict:
    sys.path.insert(0, str(ROOT))
    from app.config import Settings
    from app.integrations.mock.corridor import MockNewsSource, MockNodeSource, MockReportSource
    from app.integrations.mock.fleet import MockFleetSource, MockShipmentSource
    from app.integrations.mock.story import DemoStory
    from app.integrations.mock.wind import MockWindField
    from app.services.map_snapshot import LiveInfo, MapSnapshotService
    from app.services.weather_predictor import WindThresholds

    clock = lambda: at  # noqa: E731
    # пороги по умолчанию, не из .env
    thresholds = WindThresholds.from_settings(Settings(_env_file=None))
    plot = DemoStory(lambda: at - timedelta(hours=STORM_AFTER_H)) if story else None
    service = MapSnapshotService(
        nodes=MockNodeSource(clock, thresholds, story=plot),
        vessels=MockFleetSource(clock),
        shipments=MockShipmentSource(clock, story=plot),
        wind=MockWindField(clock),
        news=MockNewsSource(clock),
        reports=MockReportSource(clock),
        thresholds=thresholds,
        mock=True,
        clock=clock,
        live=LiveInfo(**live),
    )
    return asyncio.run(service.snapshot(at)).model_dump(mode="json")


def main() -> None:
    snapshot_path = FIXTURES / "snapshot.json"
    old = json.loads(snapshot_path.read_text())
    at = datetime.fromisoformat(old["server_time"].replace("Z", "+00:00"))
    snapshot = _snapshot(at, old["live"])
    refs = [s["ref"] for s in snapshot["shipments"]]
    assert refs == list(REFS), refs
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")
    for shipment in snapshot["shipments"]:
        _write(f"shipment_{shipment['ref']}", shipment)

    # Публичный 0501 (без истории) на пароме «Shahdag»: позиция — AIS парома
    from app.integrations.mock.fleet import east_departure

    on_ferry = east_departure(at) + timedelta(hours=FERRY_AFTER_H)
    ferry = _snapshot(on_ferry, old["live"], story=False)
    s0501 = next(s for s in ferry["shipments"] if s["ref"] == REFS[0])
    assert s0501["position"]["source"] == "ais", s0501["position"]
    _write(f"shipment_{REFS[0]}_ferry", s0501)


def _write(name: str, data: dict) -> None:
    (FIXTURES / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
