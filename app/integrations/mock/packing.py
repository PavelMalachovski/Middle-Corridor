"""Демо-пакинг-листы грузов мока (коды ТН ВЭД) — для проверки по санкционным спискам.

Время получения листа — относительно «сейчас» мока (как и остальные события), поэтому
статус проверки груза в replay не меняется — так же, как его положение.

Сценарии: 0431 — среди автозапчастей стальной прокат российского происхождения
(прил. XVII 833/2014) → «возможна санкционка»; 0412 — процессоры из CHPL, получатель в
Венгрии → «проверить вручную»; 0447 и 0455 — листа нет (прошёл Хоргос / ещё в Китае).
Остальные — чистые: совпадения с запретами ввоза при известном не-РФ происхождении
идут только справкой.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.sanctions import PackingLine, PackingList
from app.services.tracking import ShipmentPlan

_DEST_COUNTRY = {"BUDAPEST": "HU", "CONSTANTA": "RO", "BUCHAREST": "RO", "KOSTANAY": "KZ"}


@dataclass(frozen=True, slots=True)
class DemoPacking:
    received_ago: timedelta
    lines: tuple[PackingLine, ...]
    consignee_country: str


def _l(no: int, code: str, ru: str, en: str, origin: str) -> PackingLine:
    return PackingLine(no, code, ru, en, origin)


DEMO_PACKING: dict[str, DemoPacking] = {
    "MC-26-0412": DemoPacking(
        timedelta(days=6),
        (
            _l(1, "8542310001", "Микросхемы-процессоры", "Processor integrated circuits", "CN"),
            _l(2, "8471300000", "Ноутбуки", "Laptops", "CN"),
            _l(3, "8517130000", "Смартфоны", "Smartphones", "CN"),
        ),
        "HU",
    ),
    "MC-26-0398": DemoPacking(
        timedelta(days=5),
        (_l(1, "3902100000", "Полипропилен в гранулах", "Polypropylene granules", "KZ"),),
        "RO",
    ),
    "MC-26-0431": DemoPacking(
        timedelta(hours=20),
        (
            _l(1, "8708301000", "Тормозные колодки", "Brake pads", "CN"),
            _l(2, "8708809900", "Амортизаторы", "Shock absorbers", "CN"),
            _l(3, "7208511000", "Прокат плоский горячекатаный", "Hot-rolled flat steel", "RU"),
            _l(4, "4011100003", "Шины легковые", "Passenger car tyres", "CN"),
            _l(5, "8512200009", "Фары", "Headlamps", "CN"),
        ),
        "HU",
    ),
    "MC-26-0377": DemoPacking(
        timedelta(days=4),
        (_l(1, "8541430000", "Фотоэлектрические модули", "Photovoltaic modules", "CN"),),
        "HU",
    ),
    "MC-26-0365": DemoPacking(
        timedelta(days=5),
        (_l(1, "0811909500", "Ягоды замороженные", "Frozen berries", "CN"),),
        "HU",
    ),
    "MC-26-0351": DemoPacking(
        timedelta(days=7),
        (
            _l(1, "8418102001", "Холодильники бытовые", "Household refrigerators", "CN"),
            _l(2, "8450111100", "Стиральные машины", "Washing machines", "CN"),
        ),
        "RO",
    ),
    "MC-26-0322": DemoPacking(
        timedelta(days=12),
        (_l(1, "6109100000", "Футболки хлопковые", "Cotton T-shirts", "CN"),),
        "HU",
    ),
    # Восток: коды — из настоящей экспортной декларации автокомплектов (данные обезличены).
    # Чешский крепёж и запчасти в Казахстан — не запрет ввоза в ЕС и не прил. XXIII без
    # связи с РФ → «чисто»; разъёмы из CHPL → «проверить вручную» (риск реэкспорта).
    "MC-26-0501": DemoPacking(
        timedelta(days=9),
        (
            _l(1, "8708509140", "Мост задний ведущий", "Rear drive axle", "CZ"),
            _l(2, "8708299040", "Детали кузова", "Body parts", "CZ"),
            _l(3, "7318158800", "Болты стальные", "Steel bolts", "CZ"),
            _l(4, "3926909700", "Изделия из пластмасс", "Plastic parts", "CZ"),
            _l(5, "9027101040", "Лямбда-зонд", "Lambda probe", "CZ"),
            _l(6, "8507100000", "Аккумуляторы", "Batteries", "DE"),
        ),
        "KZ",
    ),
    "MC-26-0502": DemoPacking(
        timedelta(days=4),
        (
            _l(1, "8536699008", "Разъёмы электрические", "Electrical connectors", "DE"),
            _l(2, "8544429009", "Жгуты проводов", "Wiring harnesses", "CZ"),
            _l(3, "8512200009", "Фары", "Headlamps", "CZ"),
        ),
        "KZ",
    ),
    "MC-26-0405": DemoPacking(
        timedelta(days=3),
        (_l(1, "7202410000", "Феррохром", "Ferro-chromium", "KZ"),),
        "RO",
    ),
}


def with_packing(plan: ShipmentPlan, now: datetime) -> ShipmentPlan:
    """План с демо-пакинг-листом (если он у груза есть)."""
    demo = DEMO_PACKING.get(plan.ref)
    if demo is None:
        return plan
    packing = PackingList(
        received_at=now - demo.received_ago,
        lines=demo.lines,
        consignee_country=demo.consignee_country,
        destination_country=_DEST_COUNTRY.get(plan.route[-1]),
    )
    return dataclasses.replace(plan, packing_list=packing)
