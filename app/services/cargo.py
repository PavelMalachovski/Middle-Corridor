"""Сведения о грузе для карточки: контейнер, вес, места, главные позиции, опасный груз.

Источники — букинг, лист погрузки, инвойс, декларация опасного груза (DGD). Наружу —
только то, что нужно для перевозки: стоимость, получатель, пломбы и полный список позиций
в публичный ответ не идут (номер груза знает кто угодно, а снимок отдаёт все грузы).
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.services.sanctions import PackingList

TOP_ITEMS = 5


@dataclass(frozen=True, slots=True)
class DangerousGoods:
    un_number: str  # «2800»
    hazard_class: str  # «8»
    description: str
    description_en: str | None = None
    gross_kg: float | None = None


@dataclass(frozen=True, slots=True)
class CargoManifest:
    """Сведения уровня отправки (букинг, лист погрузки, DGD) — без позиций."""

    container_no: str | None = None
    container_type: str | None = None  # «40' HC»
    packages: int | None = None
    package_kind: str | None = None  # «поддоны»
    package_kind_en: str | None = None
    gross_kg: float | None = None
    net_kg: float | None = None
    description: str | None = None
    description_en: str | None = None
    dangerous: tuple[DangerousGoods, ...] = ()


class CargoItem(BaseModel):
    description: str
    description_en: str | None = None
    hs_code: str
    quantity: float | None = None
    net_kg: float | None = None


class DangerousGoodsInfo(BaseModel):
    un_number: str
    hazard_class: str
    description: str
    description_en: str | None = None
    gross_kg: float | None = None


class CargoDetails(BaseModel):
    container_no: str | None = None
    container_type: str | None = None
    packages: int | None = None
    package_kind: str | None = None
    package_kind_en: str | None = None
    gross_kg: float | None = None
    net_kg: float | None = None
    description: str | None = None
    description_en: str | None = None
    top_items: list[CargoItem] = []  # главные позиции по весу нетто
    more_items: int = 0  # сколько позиций не показано
    dangerous: list[DangerousGoodsInfo] = []


def cargo_details(
    manifest: CargoManifest | None,
    packing_list: PackingList | None,
    *,
    at: datetime,
    top: int = TOP_ITEMS,
) -> CargoDetails | None:
    """Блок «Груз»; позиции — только из пакинг-листа, полученного к моменту `at`."""
    lines = packing_list.lines if packing_list and packing_list.received_at <= at else ()
    if manifest is None and not lines:
        return None
    ranked = sorted(lines, key=lambda x: (x.net_kg is None, -(x.net_kg or 0), x.no))
    items = [
        CargoItem(
            description=x.description,
            description_en=x.description_en,
            hs_code="".join(ch for ch in x.hs_code if ch.isdigit()),
            quantity=x.quantity,
            net_kg=x.net_kg,
        )
        for x in ranked[:top]
    ]
    m = manifest or CargoManifest()
    return CargoDetails(
        container_no=m.container_no,
        container_type=m.container_type,
        packages=m.packages,
        package_kind=m.package_kind,
        package_kind_en=m.package_kind_en,
        gross_kg=m.gross_kg,
        net_kg=m.net_kg,
        description=m.description,
        description_en=m.description_en,
        top_items=items,
        more_items=max(len(ranked) - top, 0),
        dangerous=[
            DangerousGoodsInfo(
                un_number=g.un_number,
                hazard_class=g.hazard_class,
                description=g.description,
                description_en=g.description_en,
                gross_kg=g.gross_kg,
            )
            for g in m.dangerous
        ],
    )
