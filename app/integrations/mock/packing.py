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

from app.services.cargo import CargoManifest, DangerousGoods
from app.services.sanctions import PackingLine, PackingList
from app.services.tracking import ShipmentPlan

_DEST_COUNTRY = {"BUDAPEST": "HU", "CONSTANTA": "RO", "BUCHAREST": "RO", "KOSTANAY": "KZ"}


@dataclass(frozen=True, slots=True)
class DemoPacking:
    received_ago: timedelta
    lines: tuple[PackingLine, ...]
    consignee_country: str


def _l(
    no: int,
    code: str,
    ru: str,
    en: str,
    origin: str,
    qty: float | None = None,
    net_kg: float | None = None,
) -> PackingLine:
    return PackingLine(no, code, ru, en, origin, qty, net_kg)


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
            _l(1, "8708509140", "Мост задний ведущий", "Rear drive axle", "CZ", 14, 1680),
            _l(2, "8708299040", "Детали кузова", "Body parts", "CZ", 14, 69),
            _l(3, "7318158800", "Болты стальные", "Steel bolts", "CZ", 28, 67),
            _l(4, "3926909700", "Изделия из пластмасс", "Plastic parts", "CZ", 224, 12),
            _l(5, "9027101040", "Лямбда-зонд", "Lambda probe", "CZ", 14, 5),
            _l(6, "8507100000", "Аккумуляторы", "Batteries", "DE", 14, 259),
            _l(
                7,
                "8708999740",
                "Агрегат: двигатель и КПП",
                "Engine and gearbox unit",
                "CZ",
                14,
                5481,
            ),
            _l(8, "8708705099", "Колесо в сборе", "Wheel with tyre", "CZ", 70, 1813),
            _l(9, "8708923599", "Глушитель", "Exhaust silencer", "CZ", 14, 165),
        ),
        "KZ",
    ),
    "MC-26-0502": DemoPacking(
        timedelta(days=4),
        (
            _l(1, "8536699008", "Разъёмы электрические", "Electrical connectors", "DE", 4000, 380),
            _l(2, "8544429009", "Жгуты проводов", "Wiring harnesses", "CZ", 300, 2900),
            _l(3, "8512200009", "Фары", "Headlamps", "CZ", 120, 320),
        ),
        "KZ",
    ),
    "MC-26-0405": DemoPacking(
        timedelta(days=3),
        (_l(1, "7202410000", "Феррохром", "Ferro-chromium", "KZ"),),
        "RO",
    ),
}


# Сведения уровня отправки (букинг, лист погрузки, DGD) — по образцу автокомплектов,
# номера контейнеров вымышлены
DEMO_MANIFEST: dict[str, CargoManifest] = {
    "MC-26-0501": CargoManifest(
        container_no="DEMU5010012",
        container_type="40' HC",
        packages=14,
        package_kind="поддоны",
        package_kind_en="pallets",
        gross_kg=12449,
        net_kg=9551,
        description="Автокомплекты для промышленной сборки",
        description_en="Car assembly kits",
        dangerous=(
            DangerousGoods(
                "2800",
                "8",
                "Аккумуляторы с электролитом, непроливные",
                "Batteries, wet, non-spillable",
                273,
            ),
        ),
    ),
    "MC-26-0502": CargoManifest(
        container_no="DEMU5020027",
        container_type="40' HC",
        packages=6,
        package_kind="поддоны",
        package_kind_en="pallets",
        gross_kg=4210,
        net_kg=3600,
        description="Электрооборудование для сборки автомобилей",
        description_en="Electrical parts for car assembly",
    ),
}


def with_packing(plan: ShipmentPlan, now: datetime) -> ShipmentPlan:
    """План с демо-пакинг-листом (если он у груза есть)."""
    manifest = DEMO_MANIFEST.get(plan.ref)
    if manifest is not None:
        plan = dataclasses.replace(plan, cargo_manifest=manifest)
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
