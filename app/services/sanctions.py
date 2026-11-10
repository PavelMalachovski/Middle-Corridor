"""Проверка пакинг-листа по санкционным спискам (коды ТН ВЭД × CHPL, ЕС 833/2014).

Флаг — подсказка для ручной проверки, не юридическое заключение. Списки — данные
в app/data/sanctions (CSV + lists.json) с источником и датой; обновляет их человек.
Модуль не импортирует tracking — наоборот, tracking зовёт screen().
"""

import csv
import enum
import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "sanctions"
_COLUMNS = ("code", "item_en", "ref", "measure", "countries")


class Measure(enum.StrEnum):
    export_ban = "export_ban"  # нельзя везти в страну из countries (CHPL)
    import_ban = "import_ban"  # нельзя ввозить в ЕС товар происхождения countries


@dataclass(frozen=True, slots=True)
class SanctionsEntry:
    list_id: str
    code: str  # 4–8 цифр без пробелов
    item_en: str
    ref: str  # Tier для CHPL, приложение для ЕС
    measure: Measure
    countries: frozenset[str]


class SanctionsListInfo(BaseModel):
    code: str
    name: str
    name_en: str
    as_of: date
    source_url: str
    # совпадение кода без связи с РФ/РБ — «проверить вручную» (CHPL: товары, которые чаще
    # всего уходят в РФ через третьи страны); у остальных списков такое совпадение не в счёт
    review_code_only: bool = False


# Запрет ввоза (прил. XVII, XXI) касается только ввоза в ЕС
EU_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split()
)


@dataclass(frozen=True, slots=True)
class SanctionsLists:
    infos: tuple[SanctionsListInfo, ...]
    entries: tuple[SanctionsEntry, ...]


def _digits(code: str) -> str:
    return "".join(ch for ch in code if not ch.isspace() and ch != ".")


def _entry(list_id: str, row: dict[str, str], where: str) -> SanctionsEntry:
    code = _digits(row.get("code") or "")
    if not (code.isdigit() and 4 <= len(code) <= 8):
        raise ValueError(f"{where}: код должен быть 4–8 цифр, а не {row.get('code')!r}")
    try:
        measure = Measure(row.get("measure") or "")
    except ValueError:
        raise ValueError(f"{where}: неизвестная measure {row.get('measure')!r}") from None
    raw_countries = (row.get("countries") or "").split(";")
    countries = frozenset(c.strip().upper() for c in raw_countries if c.strip())
    if not countries or any(len(c) != 2 for c in countries):
        raise ValueError(f"{where}: countries — ISO-2 через «;», а не {row.get('countries')!r}")
    item_en, ref = (row.get("item_en") or "").strip(), (row.get("ref") or "").strip()
    if not item_en or not ref:
        raise ValueError(f"{where}: пустые item_en/ref")
    return SanctionsEntry(list_id, code, item_en, ref, measure, countries)


def load_lists(directory: Path = DATA_DIR) -> SanctionsLists:
    """Читает lists.json и CSV списков; на ошибке — ValueError с файлом и строкой."""
    meta = json.loads((directory / "lists.json").read_text(encoding="utf-8"))
    infos: list[SanctionsListInfo] = []
    entries: list[SanctionsEntry] = []
    for item in meta:
        infos.append(SanctionsListInfo.model_validate(item))
        path = directory / item["file"]
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if tuple(reader.fieldnames or ()) != _COLUMNS:
                raise ValueError(f"{path.name}: колонки должны быть {','.join(_COLUMNS)}")
            for row in reader:
                entries.append(_entry(item["code"], row, f"{path.name}:{reader.line_num}"))
    # в приложениях бывают повторы одного кода (поправки) — одна запись на код в списке
    unique = {(e.list_id, e.code): e for e in reversed(entries)}
    return SanctionsLists(
        tuple(infos), tuple(e for e in entries if unique[(e.list_id, e.code)] is e)
    )


@cache
def default_lists() -> SanctionsLists:
    return load_lists()


# --- Пакинг-лист и сверка -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackingLine:
    no: int
    hs_code: str  # ТН ВЭД ЕАЭС, 10 цифр (пробелы и точки допустимы)
    description: str
    description_en: str | None = None
    origin_country: str | None = None  # ISO-2
    quantity: float | None = None  # штук (для блока «Груз»)
    net_kg: float | None = None


@dataclass(frozen=True, slots=True)
class PackingList:
    received_at: datetime
    lines: tuple[PackingLine, ...]
    consignee_country: str | None = None  # ISO-2
    destination_country: str | None = None  # ISO-2


class SanctionsStatus(enum.StrEnum):
    pending = "pending"  # листа нет, граница Казахстана впереди
    missing = "missing"  # листа нет, а Хоргос пройден
    clear = "clear"  # совпадений, требующих внимания, нет
    review = "review"  # только слабые совпадения — проверить вручную
    flagged = "flagged"  # код из списка + связь с РФ/РБ


class SanctionsMatch(BaseModel):
    line_no: int
    hs_code: str
    description: str
    description_en: str | None = None
    origin_country: str | None = None
    list_id: str
    list_code: str  # исходный код записи списка
    ref: str
    measure: Measure
    strong: bool
    # origin_ru | consignee_ru | code_only (export_ban) | steel_inputs | no_origin | no_consignee
    reason_code: str


class SanctionsCheck(BaseModel):
    status: SanctionsStatus
    checked_at: datetime | None = None
    lists: list[SanctionsListInfo]
    matches: list[SanctionsMatch]


# Прил. XVII: запрет ввоза распространяется и на сталь, обработанную в третьей стране из
# российских заготовок (ст. 3g(1)(d)) — известное не-РФ происхождение не снимает вопрос.
_PROCESSED_INPUT_REFS = frozenset({"Annex XVII"})


def _strength(entry: SanctionsEntry, line: PackingLine, pl: PackingList) -> tuple[bool, str]:
    if entry.measure == Measure.import_ban:
        origin = (line.origin_country or "").upper()
        if not origin:
            return False, "no_origin"
        if origin in entry.countries:
            return True, "origin_ru"
        return False, "steel_inputs" if entry.ref in _PROCESSED_INPUT_REFS else "code_only"
    parties = {c.upper() for c in (pl.consignee_country, pl.destination_country) if c}
    if not parties:
        return False, "no_consignee"
    return (True, "consignee_ru") if parties & entry.countries else (False, "code_only")


def _relevant(m: SanctionsMatch, review_lists: frozenset[str]) -> bool:
    """Совпадение, из-за которого есть статус: сильное или «проверить вручную».

    Код без связи с РФ/РБ — не совпадение, кроме списков с `review_code_only` (CHPL).
    Прил. XXI и XXIII покрывают почти любую электронику, пластик, автозапчасти и станки:
    иначе «проверить вручную» стояло бы на каждом контейнере, а ответ раскрыл бы весь лист.
    """
    return m.strong or m.reason_code != "code_only" or m.list_id in review_lists


def _applies(entry: SanctionsEntry, pl: PackingList) -> bool:
    """Запрет ввоза — только для груза в ЕС (назначение не указано — проверяем)."""
    if entry.measure != Measure.import_ban:
        return True
    dest = (pl.destination_country or "").upper()
    return not dest or dest in EU_COUNTRIES


def screen(
    packing_list: PackingList | None,
    *,
    border_reached: bool,
    at: datetime,
    lists: SanctionsLists,
) -> SanctionsCheck:
    """Статус проверки и совпавшие позиции; остальные позиции листа наружу не идут."""
    infos = list(lists.infos)
    if packing_list is None or at < packing_list.received_at:
        status = SanctionsStatus.missing if border_reached else SanctionsStatus.pending
        return SanctionsCheck(status=status, lists=infos, matches=[])

    review_lists = frozenset(i.code for i in lists.infos if i.review_code_only)
    matches: list[SanctionsMatch] = []
    seen: set[tuple[int, str, str]] = set()
    for line in sorted(packing_list.lines, key=lambda x: x.no):
        code = _digits(line.hs_code)
        for entry in lists.entries:
            key = (line.no, entry.list_id, entry.code[:6])  # КН-8 сверяем по 6 знакам
            if key in seen or not code.startswith(entry.code[:6]):
                continue
            if not _applies(entry, packing_list):
                continue
            seen.add(key)
            strong, reason = _strength(entry, line, packing_list)
            matches.append(
                SanctionsMatch(
                    line_no=line.no,
                    hs_code=code,
                    description=line.description,
                    description_en=line.description_en,
                    origin_country=line.origin_country,
                    list_id=entry.list_id,
                    list_code=entry.code,
                    ref=entry.ref,
                    measure=entry.measure,
                    strong=strong,
                    reason_code=reason,
                )
            )
    matches = [m for m in matches if _relevant(m, review_lists)]
    matches.sort(key=lambda m: (not m.strong, m.line_no))  # сортировка устойчивая
    if any(m.strong for m in matches):
        status = SanctionsStatus.flagged
    elif matches:
        status = SanctionsStatus.review
    else:
        status = SanctionsStatus.clear
    return SanctionsCheck(
        status=status, checked_at=packing_list.received_at, lists=infos, matches=matches
    )
