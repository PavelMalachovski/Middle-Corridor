"""Проверка пакинг-листа по санкционным спискам (коды ТН ВЭД × CHPL, ЕС 833/2014).

Флаг — подсказка для ручной проверки, не юридическое заключение. Списки — данные
в app/data/sanctions (CSV + lists.json) с источником и датой; обновляет их человек.
Модуль не импортирует tracking — наоборот, tracking зовёт screen().
"""

import csv
import enum
import json
from dataclasses import dataclass
from datetime import date
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
    return SanctionsLists(tuple(infos), tuple(entries))


@cache
def default_lists() -> SanctionsLists:
    return load_lists()
