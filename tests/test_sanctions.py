"""Сверка пакинг-листа со списками: статусы, сила совпадения, нормализация кодов."""

from datetime import UTC, date, datetime, timedelta

from app.services.sanctions import (
    Measure,
    PackingLine,
    PackingList,
    SanctionsEntry,
    SanctionsListInfo,
    SanctionsLists,
    SanctionsStatus,
    screen,
)

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
STEEL = SanctionsEntry(
    "eu", "72085120", "flat-rolled", "Annex XVII", Measure.import_ban, frozenset({"RU"})
)
STEEL4 = SanctionsEntry(
    "eu", "7208", "flat-rolled", "Annex XVII", Measure.import_ban, frozenset({"RU"})
)
CHIPS = SanctionsEntry(
    "chpl", "854231", "ICs", "Tier 1", Measure.export_ban, frozenset({"RU", "BY"})
)
INFOS = (
    SanctionsListInfo(
        code="eu", name="ЕС", name_en="EU", as_of=date(2026, 7, 24), source_url="https://x"
    ),
    SanctionsListInfo(
        code="chpl", name="CHPL", name_en="CHPL", as_of=date(2026, 7, 24), source_url="https://x"
    ),
)
LISTS = SanctionsLists(INFOS, (STEEL, CHIPS))


def _list(
    *lines: PackingLine, consignee: str | None = "HU", dest: str | None = "HU"
) -> PackingList:
    return PackingList(
        received_at=NOW - timedelta(hours=6),
        lines=lines,
        consignee_country=consignee,
        destination_country=dest,
    )


def _screen(pl: PackingList | None, border: bool = False, at: datetime = NOW, lists=LISTS):
    return screen(pl, border_reached=border, at=at, lists=lists)


TOYS = PackingLine(1, "9503007000", "Игрушки", origin_country="CN")


def test_no_list_before_border_is_pending() -> None:
    check = _screen(None)
    assert check.status == SanctionsStatus.pending and check.checked_at is None


def test_no_list_after_border_is_missing() -> None:
    assert _screen(None, border=True).status == SanctionsStatus.missing


def test_list_after_border_wins_over_missing() -> None:
    check = _screen(_list(TOYS), border=True)
    assert check.status == SanctionsStatus.clear
    assert check.checked_at == NOW - timedelta(hours=6)
    assert [i.code for i in check.lists] == ["eu", "chpl"]


def test_received_later_than_at_counts_as_absent() -> None:
    early = NOW - timedelta(hours=12)
    assert _screen(_list(TOYS), at=early).status == SanctionsStatus.pending
    check = _screen(_list(TOYS), border=True, at=early)
    assert check.status == SanctionsStatus.missing and check.checked_at is None


def test_cn8_matches_on_six_digits() -> None:
    line = PackingLine(3, "7208519800", "Прокат", origin_country="RU")
    m = _screen(_list(line)).matches
    assert len(m) == 1 and m[0].list_code == "72085120" and m[0].list_id == "eu"


def test_four_digit_code_matches_by_prefix() -> None:
    lists = SanctionsLists(INFOS, (STEEL4,))
    line = PackingLine(1, "7208390000", "Прокат", origin_country="RU")
    assert _screen(_list(line), lists=lists).matches[0].list_code == "7208"


def test_codes_normalized() -> None:
    steel = PackingLine(1, "7208 51 200 0", "Прокат", origin_country="RU")
    chips = PackingLine(2, "8542.31.000.1", "Микросхемы", origin_country="CN")
    m = _screen(_list(steel, chips)).matches
    assert {x.list_id for x in m} == {"eu", "chpl"}
    assert {x.hs_code for x in m} == {"7208512000", "8542310001"}


def test_import_ban_strong_only_for_listed_origin() -> None:
    def one(origin: str | None):
        return _screen(
            _list(PackingLine(1, "7208519800", "Прокат", origin_country=origin))
        ).matches[0]

    ru = one("RU")
    assert ru.strong and ru.reason_code == "origin_ru" and ru.measure == Measure.import_ban
    cn = one("CN")
    assert not cn.strong and cn.reason_code == "code_only"
    unknown = one(None)
    assert not unknown.strong and unknown.reason_code == "no_origin"


def test_export_ban_strong_by_consignee_or_destination() -> None:
    chips = PackingLine(1, "8542310001", "Микросхемы", origin_country="CN")

    def one(consignee: str | None, dest: str | None):
        return _screen(_list(chips, consignee=consignee, dest=dest)).matches[0]

    assert one("BY", "HU").strong and one("BY", "HU").reason_code == "consignee_ru"
    assert one("KZ", "RU").strong and one("KZ", "RU").reason_code == "consignee_ru"
    assert not one("HU", "HU").strong and one("HU", "HU").reason_code == "code_only"
    assert one(None, None).reason_code == "no_consignee"


def test_status_review_vs_flagged() -> None:
    chips_eu = PackingLine(1, "8542310001", "Микросхемы", origin_country="CN")
    assert _screen(_list(chips_eu)).status == SanctionsStatus.review
    steel_ru = PackingLine(2, "7208519800", "Прокат", origin_country="RU")
    assert _screen(_list(chips_eu, steel_ru)).status == SanctionsStatus.flagged


def test_import_ban_with_known_other_origin_is_info_only() -> None:
    """Ruling: запрет ввоза «по происхождению» — известное не-РФ происхождение не ставит review."""
    steel_cn = PackingLine(1, "7208519800", "Прокат", origin_country="CN")
    check = _screen(_list(steel_cn))
    assert check.status == SanctionsStatus.clear
    assert len(check.matches) == 1 and check.matches[0].reason_code == "code_only"


def test_unknown_origin_on_import_ban_needs_review() -> None:
    steel = PackingLine(1, "7208519800", "Прокат")
    assert _screen(_list(steel)).status == SanctionsStatus.review


def test_one_line_two_lists() -> None:
    both = SanctionsEntry("eu", "8542", "ICs", "Annex XXI", Measure.import_ban, frozenset({"RU"}))
    lists = SanctionsLists(INFOS, (both, CHIPS))
    line = PackingLine(1, "8542310001", "Микросхемы", origin_country="RU")
    m = _screen(_list(line), lists=lists).matches
    assert [x.list_id for x in m] == ["eu", "chpl"]  # сильное (RU-происхождение) первым
    assert m[0].strong and not m[1].strong


def test_route_without_border_never_missing() -> None:
    far = NOW + timedelta(days=30)
    assert _screen(None, border=False, at=far).status == SanctionsStatus.pending


def test_matches_only_matched_lines() -> None:
    lines = [
        PackingLine(i, f"9503{i:06d}", f"Позиция {i}", origin_country="CN") for i in range(1, 5)
    ]
    lines.append(PackingLine(5, "7208519800", "Прокат", origin_country="RU"))
    check = _screen(_list(*lines))
    assert len(check.matches) == 1 and check.matches[0].line_no == 5
