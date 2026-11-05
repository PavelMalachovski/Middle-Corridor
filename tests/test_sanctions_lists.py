"""Санкционные списки — файлы данных с источником (app/data/sanctions)."""

from pathlib import Path

import pytest

from app.services.sanctions import Measure, default_lists, load_lists


def test_default_lists_load_and_are_valid() -> None:
    lists = default_lists()
    assert {i.code for i in lists.infos} == {"chpl", "eu_833_2014"}
    for info in lists.infos:
        assert info.source_url.startswith("https://") and info.as_of.year >= 2025
        assert info.name and info.name_en
    for e in lists.entries:
        assert e.code.isdigit() and 4 <= len(e.code) <= 8, e
        assert e.item_en and e.ref

    chpl = [e for e in lists.entries if e.list_id == "chpl"]
    assert len(chpl) == 50 and all(len(e.code) == 6 for e in chpl)
    assert all(e.measure == Measure.export_ban and e.countries == {"RU", "BY"} for e in chpl)
    tiers = {"Tier 1", "Tier 2", "Tier 3.A", "Tier 3.B", "Tier 4.A", "Tier 4.B"}
    assert {e.ref for e in chpl} == tiers

    eu = [e for e in lists.entries if e.list_id == "eu_833_2014"]
    assert all(e.measure == Measure.import_ban and e.countries == {"RU"} for e in eu)
    assert sum(e.ref == "Annex XVII" for e in eu) == 50
    assert sum(e.ref == "Annex XXI" for e in eu) == 267


def test_known_entries_present() -> None:
    codes = {(e.list_id, e.code) for e in default_lists().entries}
    assert ("chpl", "854231") in codes  # Tier 1: процессоры и контроллеры
    assert ("chpl", "848210") in codes  # Tier 3.B: шарикоподшипники
    assert ("eu_833_2014", "7208") in codes  # прил. XVII: горячекатаный плоский прокат
    assert ("eu_833_2014", "16043100") in codes  # прил. XXI: икра


def _write(tmp_path: Path, rows: str) -> Path:
    (tmp_path / "lists.json").write_text(
        '[{"code": "x", "name": "X", "name_en": "X", "as_of": "2026-01-01",'
        ' "source_url": "https://example.org", "file": "x.csv"}]'
    )
    (tmp_path / "x.csv").write_text("code,item_en,ref,measure,countries\n" + rows)
    return tmp_path


def test_bad_code_rejected_with_line(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"x\.csv:2"):
        load_lists(_write(tmp_path, "84A1,Bad,Tier 1,export_ban,RU\n"))


def test_unknown_measure_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="measure"):
        load_lists(_write(tmp_path, "8471,Ok,Tier 1,ban,RU\n"))


def test_code_spaces_normalized(tmp_path: Path) -> None:
    lists = load_lists(_write(tmp_path, "8542 31,ICs,Tier 1,export_ban,RU;BY\n"))
    assert lists.entries[0].code == "854231"
    assert lists.entries[0].countries == {"RU", "BY"}
