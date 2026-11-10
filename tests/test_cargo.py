"""Сведения о грузе для карточки: контейнер, вес, места, главные позиции, опасный груз."""

from datetime import UTC, datetime, timedelta

from app.services.cargo import CargoManifest, DangerousGoods, cargo_details
from app.services.sanctions import PackingLine, PackingList

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
MANIFEST = CargoManifest(
    container_no="DEMU5010012",
    container_type="40' HC",
    packages=14,
    package_kind="поддоны",
    package_kind_en="pallets",
    gross_kg=12449.0,
    net_kg=9551.0,
    description="Автокомплекты для промышленной сборки",
    description_en="Car assembly kits",
    dangerous=(
        DangerousGoods("2800", "8", "Аккумуляторы непроливные", "Batteries, non-spillable", 273.0),
    ),
)


def _line(no: int, net: float | None, qty: float | None = 1) -> PackingLine:
    return PackingLine(no, f"8708{no:06d}", f"Позиция {no}", f"Item {no}", "CZ", qty, net)


def _list(*lines: PackingLine, hours_ago: float = 5) -> PackingList:
    return PackingList(NOW - timedelta(hours=hours_ago), lines, "KZ", "KZ")


def test_nothing_known_is_none() -> None:
    assert cargo_details(None, None, at=NOW) is None


def test_manifest_without_packing_list() -> None:
    d = cargo_details(MANIFEST, None, at=NOW)
    assert d is not None and d.container_no == "DEMU5010012" and d.packages == 14
    assert d.top_items == [] and d.more_items == 0
    assert [(g.un_number, g.hazard_class) for g in d.dangerous] == [("2800", "8")]


def test_top_items_by_net_weight_and_rest_counted() -> None:
    lines = [_line(i, w) for i, w in enumerate([5, 1680, None, 69, 5481, 1813, 165], start=1)]
    d = cargo_details(MANIFEST, _list(*lines), at=NOW)
    assert d is not None
    assert [i.description for i in d.top_items] == [
        "Позиция 5",
        "Позиция 6",
        "Позиция 2",
        "Позиция 7",
        "Позиция 4",
    ]
    assert d.more_items == 2
    assert d.top_items[0].net_kg == 5481 and d.top_items[0].hs_code == "8708000005"


def test_packing_list_not_yet_received_gives_no_items() -> None:
    d = cargo_details(MANIFEST, _list(_line(1, 10), hours_ago=-3), at=NOW)
    assert d is not None and d.top_items == [] and d.more_items == 0


def test_packing_list_without_manifest_still_shows_items() -> None:
    d = cargo_details(None, _list(_line(1, 10)), at=NOW)
    assert d is not None and d.container_no is None and len(d.top_items) == 1


def test_no_commercial_value_in_response() -> None:
    d = cargo_details(MANIFEST, _list(_line(1, 10)), at=NOW)
    dumped = d.model_dump() if d else {}
    assert not {"value", "price", "amount", "consignee", "seals"} & dumped.keys()
