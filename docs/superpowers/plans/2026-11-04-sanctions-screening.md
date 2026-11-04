# Проверка грузов на санкции — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Коды ТН ВЭД из пакинг-листа демо-грузов сверяются со списками CHPL и ЕС 833/2014; iOS предупреждает «возможна санкционка» (код + связь с РФ/РБ) и «прошёл Хоргос без пакинг-листа».

**Architecture:** Бэкенд: списки — CSV + `lists.json` в `app/data/sanctions/`, загрузка и проверка — `app/services/sanctions.py` (чистые функции, не импортирует `tracking`); `ShipmentPlan.packing_list` → `project_shipment` → поле `Shipment.sanctions` в `/api/v1`. iOS: модели и правило уведомления в MCCore (`swift test`), набор отправленных `id` — в приложении (`UserDefaults`), блок в карточке и пометка в строке списка.

**Tech Stack:** Python 3.11/FastAPI/pydantic/pytest; Swift 6, SwiftUI, XCTest/XCUITest.

**Spec:** `docs/superpowers/specs/2026-11-04-sanctions-screening-design.md`; правила — `CLAUDE.md`.

## Global Constraints

- Флаг — не вердикт: в текстах «возможна», «проверьте вручную»; блок карточки кончается строкой «Это подсказка, а не юридическое заключение».
- Записи списков — только из официальных текстов (страница CHPL Еврокомиссии, консолидированный 833/2014 на EUR-Lex), у каждого списка `source_url` и `as_of`; неподтверждённую запись не добавлять.
- Коды списков — 4–8 цифр; код из 8 цифр сравнивается по первым 6; код из ≤ 6 — префиксом 10-значного ТН ВЭД.
- `countries`: CHPL — `RU,BY`; ЕС 833/2014 — `RU`.
- Статусы: `pending`, `missing`, `clear`, `review`, `flagged`; `reason_code`: `origin_ru`, `consignee_ru`, `code_only`, `no_origin`, `no_consignee` (суффикс `_ru` означает «страна из `countries`», для BY — тот же код).
- В API — только совпавшие позиции; ключей `lines` / `packing_list` в ответе нет. Поле списка в совпадении — `list_id` (в spec — `list`: переименовано, чтобы не затенять встроенный `list` в pydantic-модели).
- Уведомление о санкциях — по текущему состоянию + набор отправленных `id`; остальные виды — по разнице, без изменений.
- iOS: новые поля API — необязательные; строки из кодов — `Strings.swift`/`Labels`, UI-заголовки — `Localizable.xcstrings`, RU и EN; цвета — `Theme`; MCCore без UI-фреймворков.
- В публичный Telegram-канал ничего; сайт и бот не трогаем.
- Команды iOS — с `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`; перед коммитом Python — `ruff check --fix . && black .`.

## Review Focus

1. Пакинг-лист пришёл **после** того, как груз прошёл Хоргос: статус сразу `clear`/`review`/`flagged`, не `missing` → тест в Task 2 (`test_list_after_border_wins_over_missing`).
2. Код ТН ВЭД в листе с точками и пробелами (`7208 51 200 0`, `8542.31.000.1`) — сопоставляется так же, как чистые цифры → тест в Task 2 (`test_codes_normalized`).
3. Груз с маршрутом без `KHORGOS` (например, из Алматы; в тесте — собранный вручную план): без листа всегда `pending`, никогда `missing` → тест в Task 2 (`test_route_without_border_never_missing`).
4. Одна позиция совпала с двумя записями (CHPL и ЕС) — в `matches` две записи, сильная первой; уведомление одно → тесты в Task 2 (`test_one_line_two_lists`) и Task 6 (`test_sanctions_one_notice_per_shipment`).
5. Удалить груз под флагом и вернуть его («Отменить» в списке) — баннера второй раз нет → тест в Task 6 (`test_sanctions_sentSet_blocksRepeat_withoutOldState`).

---

### Task 1: Санкционные списки — данные и загрузка

**Files:**
- Create: `app/data/sanctions/lists.json`, `app/data/sanctions/chpl.csv`, `app/data/sanctions/eu_833_2014.csv`
- Create: `app/services/sanctions.py` (часть: модели списков и загрузка)
- Test: `tests/test_sanctions_lists.py`

**Interfaces:**
- Produces:
  - `class Measure(StrEnum): export_ban, import_ban`
  - `@dataclass(frozen=True) class SanctionsEntry: list_id: str; code: str; item_ru: str; item_en: str; ref: str; measure: Measure; countries: frozenset[str]`
  - `class SanctionsListInfo(BaseModel): code: str; name: str; name_en: str; as_of: date; source_url: str`
  - `@dataclass(frozen=True) class SanctionsLists: infos: tuple[SanctionsListInfo, ...]; entries: tuple[SanctionsEntry, ...]`
  - `def load_lists(directory: Path = DATA_DIR) -> SanctionsLists` (кэш `functools.cache` на `default_lists() -> SanctionsLists`)

- [ ] **Step 1: Write the failing tests** (`tests/test_sanctions_lists.py`)

```python
def test_default_lists_load_and_are_valid():
    lists = default_lists()
    assert {i.code for i in lists.infos} == {"chpl", "eu_833_2014"}
    for info in lists.infos:
        assert info.source_url.startswith("https://") and info.as_of.year >= 2025
    for e in lists.entries:
        assert e.code.isdigit() and 4 <= len(e.code) <= 8, e
        assert e.item_ru and e.item_en and e.ref
    chpl = [e for e in lists.entries if e.list_id == "chpl"]
    eu = [e for e in lists.entries if e.list_id == "eu_833_2014"]
    assert 30 <= len(chpl) <= 80 and all(len(e.code) == 6 for e in chpl)
    assert all(e.measure == Measure.export_ban and e.countries == {"RU", "BY"} for e in chpl)
    assert eu and all(e.measure == Measure.import_ban and e.countries == {"RU"} for e in eu)

def test_bad_row_rejected(tmp_path):  # код с буквой / неизвестная мера → ValueError с номером строки
    ...
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_sanctions_lists.py -q` — Expected: FAIL (`ModuleNotFoundError: app.services.sanctions`).

- [ ] **Step 3: Transcribe lists from official sources**
  - CHPL: страница Еврокомиссии «Common High Priority List» (последняя редакция) — все позиции, `code` = 6 цифр HS без точек, `ref` = `Tier 1` … `Tier 4.B`, `item_ru`/`item_en` — краткое название позиции.
  - ЕС 833/2014: консолидированная редакция на EUR-Lex; приложения XVII и XXI — только строки с кодом КН/HS; `ref` = `Annex XVII` / `Annex XXI`; если запись приложения задана диапазоном или главой («ex 7208») — брать код без `ex` и указать `ex` в `item_*`. Проверить, что CHPL = приложение XL; если да — в `lists.json` у `chpl` указать это в `name` («CHPL (прил. XL к 833/2014)»).
  - `lists.json`: `[{"code", "name", "name_en", "as_of", "source_url"}]`; `as_of` — дата редакции/консолидации.
  - CSV-колонки: `code,item_ru,item_en,ref,measure,countries` (`countries` через `;`, например `RU;BY`).

- [ ] **Step 4: Implement** модели и `load_lists` в `app/services/sanctions.py`: `csv.DictReader`, нормализация кода до цифр, `ValueError(f"{file}:{line}: …")` на неверную строку; `DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "sanctions"`.

- [ ] **Step 5: Run** тест — Expected: PASS. Затем `ruff check --fix . && black .`.

- [ ] **Step 6: Commit** `git add app/data/sanctions app/services/sanctions.py tests/test_sanctions_lists.py && git commit -m "Санкции: списки CHPL и ЕС 833/2014 как данные с источником"`

---

### Task 2: Проверка пакинг-листа

**Files:**
- Modify: `app/services/sanctions.py`
- Test: `tests/test_sanctions.py`

**Interfaces:**
- Consumes: `SanctionsLists`, `SanctionsEntry`, `Measure` (Task 1)
- Produces:
  - `@dataclass(frozen=True) class PackingLine: no: int; hs_code: str; description: str; description_en: str | None = None; origin_country: str | None = None`
  - `@dataclass(frozen=True) class PackingList: received_at: datetime; lines: tuple[PackingLine, ...]; consignee_country: str | None = None; destination_country: str | None = None`
  - `class SanctionsStatus(StrEnum): pending, missing, clear, review, flagged`
  - `class SanctionsMatch(BaseModel): line_no: int; hs_code: str; description: str; description_en: str | None; origin_country: str | None; list_id: str; list_code: str; ref: str; measure: Measure; strong: bool; reason_code: str`
  - `class SanctionsCheck(BaseModel): status: SanctionsStatus; checked_at: datetime | None; lists: list[SanctionsListInfo]; matches: list[SanctionsMatch]`
  - `def screen(packing_list: PackingList | None, *, border_reached: bool, at: datetime, lists: SanctionsLists) -> SanctionsCheck`

- [ ] **Step 1: Write the failing tests** (`tests/test_sanctions.py`, списки — собранные в тесте `SanctionsLists`, не реальные файлы):

```python
STEEL = SanctionsEntry("eu", "72085120", "прокат", "flat-rolled", "Annex XVII", Measure.import_ban, frozenset({"RU"}))
CHIPS = SanctionsEntry("chpl", "854231", "ИС", "ICs", "Tier 1", Measure.export_ban, frozenset({"RU", "BY"}))

def test_no_list_before_border_is_pending(): assert screen(None, border_reached=False, ...).status == "pending"
def test_no_list_after_border_is_missing(): assert screen(None, border_reached=True, ...).status == "missing"
def test_list_after_border_wins_over_missing(): # лист есть, граница пройдена, совпадений нет → clear
def test_received_later_than_at_counts_as_absent(): # at < received_at → pending/missing, checked_at None
def test_cn8_matches_on_six_digits(): # hs 7208519800 vs 72085120 → match, list_code == "72085120"
def test_codes_normalized(): # "7208 51 200 0" и "8542.31.000.1" сопоставляются
def test_import_ban_strong_only_for_listed_origin(): # origin RU → strong/origin_ru; CN → weak/code_only; None → weak/no_origin
def test_export_ban_strong_by_consignee_or_destination(): # consignee BY → strong/consignee_ru; HU+HU → code_only; оба None → no_consignee
def test_status_review_vs_flagged(): # только слабые → review; есть сильное → flagged
def test_one_line_two_lists(): # одна позиция, две записи → 2 matches, strong первым
def test_route_without_border_never_missing(): # border_reached=False, at далеко в будущем → pending
def test_matches_only_matched_lines(): # лист из 5 позиций, совпала 1 → len(matches) == 1
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_sanctions.py -q` — Expected: FAIL (`ImportError: screen`).

- [ ] **Step 3: Implement** `screen(...)`. Порядок `matches`: сильные первыми, затем по `line_no`. `checked_at = packing_list.received_at`, если лист учтён. `lists` в ответе — все `lists.infos`.

- [ ] **Step 4: Run** — Expected: PASS; `ruff`, `black`.

- [ ] **Step 5: Commit** `git commit -m "Санкции: сверка пакинг-листа — статусы и сила совпадения"`

---

### Task 3: Пакинг-лист в плане и поле `sanctions` в API

**Files:**
- Modify: `app/services/tracking.py` (`ShipmentPlan`, `Shipment`, `project_shipment`)
- Test: `tests/test_tracking.py`

**Interfaces:**
- Consumes: `PackingList`, `SanctionsCheck`, `screen`, `default_lists` (Tasks 1–2)
- Produces: `ShipmentPlan.packing_list: PackingList | None = None`; `Shipment.sanctions: SanctionsCheck | None = None`; в `project_shipment` — `border_reached` = контрольная точка `KHORGOS` есть и её `state in {done, current}`.

- [ ] **Step 1: Write the failing tests** (`tests/test_tracking.py`):

```python
def test_sanctions_missing_after_khorgos(): # build_plan(..., ROUTE_AKTAU, arrived, "ALMATY", ...) без листа → sanctions.status == "missing"
def test_sanctions_pending_before_khorgos(): # pivot "URUMQI" → "pending"
def test_sanctions_flagged_with_russian_steel(): # dataclasses.replace(plan, packing_list=…) c кодом из default_lists() eu и origin RU → "flagged"
def test_sanctions_field_not_leaking_packing_list(): # Shipment.model_dump(): нет ключей "packing_list"/"lines"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_tracking.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement**: `sanctions=screen(plan.packing_list, border_reached=…, at=now, lists=default_lists())`. Импорт `sanctions` в `tracking` (не наоборот).
- [ ] **Step 4: Run** весь `pytest -q` — Expected: PASS (покрытие ≥ порога `pyproject`).
- [ ] **Step 5: Commit** `git commit -m "Санкции: пакинг-лист в плане груза, поле sanctions в API"`

---

### Task 4: Пакинг-листы демо-грузов

**Files:**
- Modify: `app/integrations/mock/fleet.py` (`MockShipmentSource.list_plans`; при необходимости — параметр `packing_list` в `build_plan`)
- Modify: `app/integrations/mock/story.py` (`DemoStory.plan` — чистый лист)
- Test: `tests/test_map_snapshot.py`

**Interfaces:**
- Consumes: `PackingList`, `PackingLine` (Task 2), `default_lists()` (Task 1)
- Produces: статусы демо-грузов из таблицы spec; `received_at` — относительно `now` (`at or clock()`), в прошлом.

- [ ] **Step 1: Write the failing tests:**

```python
EXPECTED = {"MC-26-0431": "flagged", "MC-26-0412": "review", "MC-26-0447": "missing", "MC-26-0455": "pending"}

async def test_mock_sanctions_statuses(mock_service):
    snap = await mock_service.snapshot()
    by_ref = {s.ref: s.sanctions.status for s in snap.shipments}
    for ref, status in by_ref.items():
        assert status == EXPECTED.get(ref, "clear"), ref

async def test_mock_packing_codes_exist_in_lists(): # у каждого совпадения демо пара (list_id, list_code) есть среди записей default_lists()

async def test_api_shipment_sanctions_without_packing_list(mock_service):
    # GET /api/v1/shipments/MC-26-0431: sanctions.status == "flagged", matches[0].strong, reason_code == "origin_ru"
    # в JSON нет "packing_list"/"lines"; len(matches) меньше числа позиций демо-листа 0431
```

Также — то же для истории: `build_map_service` с `DEMO_CONTROL=true` → у 0398 `clear` на нескольких тактах (`test_demo.py`, рядом с существующими тестами истории).

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** листы по таблице spec: 0431 («автозапчасти») — 4–6 позиций, одна — стальной прокат с кодом из `eu_833_2014.csv`, `origin_country="RU"`; 0412 — электроника с кодом из `chpl.csv`, origin `CN`, `consignee_country="HU"`; 0447 и 0455 — без листа; остальные — чистые позиции (коды вне списков), правдоподобные для своего груза.
- [ ] **Step 4: Run** `pytest -q` — Expected: PASS; `ruff`, `black`.
- [ ] **Step 5: Commit** `git commit -m "Санкции: пакинг-листы демо-грузов (0431 — возможна санкционка, 0447 — без листа)"`

---

### Task 5: iOS — модели, фикстуры, подписи

**Files:**
- Modify: `ios/MCCore/Sources/MCCore/Models.swift`, `ios/MCCore/Sources/MCCore/Labels.swift`, `ios/MCCore/Sources/MCCore/Strings.swift`, `ios/MCCore/Sources/MCCore/ShipmentGroups.swift`
- Modify: `ios/scripts/patch_fixtures.py`, фикстуры `ios/MCCore/Tests/MCCoreTests/Fixtures/{snapshot,shipment_MC-26-0398,shipment_MC-26-0412}.json`
- Test: `ios/MCCore/Tests/MCCoreTests/ModelsTests.swift`, `LabelsTests.swift`, `ShipmentGroupsTests.swift`

**Interfaces:**
- Consumes: JSON поля `sanctions` (Task 3)
- Produces (MCCore, `public`):
  - `enum SanctionsStatus: String { pending, missing, clear, review, flagged }`
  - `struct SanctionsCheck: Codable, Sendable, Hashable { status: Coded<SanctionsStatus>; checkedAt: Date?; lists: [SanctionsListInfo]; matches: [SanctionsMatch] }` + `var strongMatches: [SanctionsMatch]`
  - `struct SanctionsListInfo { code, name, nameEn: String?; asOf: String }`, `struct SanctionsMatch { lineNo: Int; hsCode, description: String; descriptionEn, originCountry: String?; listId, listCode, ref, measure: String; strong: Bool; reasonCode: String }`
  - `Shipment.sanctions: SanctionsCheck?`
  - `Labels.sanctionsStatus(_ c: SanctionsCheck) -> String`, `Labels.sanctionsMatch(_ m: SanctionsMatch, lists: [SanctionsListInfo]) -> String` («ЕС 833/2014 (Annex XVII): поз. 3, код 7208 51…, происхождение RU»), `Labels.listName(_ info:) -> String` (по языку)
  - `ShipmentGroup.of`: `flagged`/`missing` → `.attention`

- [ ] **Step 1: Write the failing tests:** декодирование фикстуры 0412 → `sanctions.status.known == .review`, `matches.count == 1`; декодирование без поля → `nil`; `Labels` RU и EN для `flagged`/`missing`/`review` и строки совпадения; `ShipmentGroup.of` с `flagged` на не задержанном грузе → `.attention`.
- [ ] **Step 2: Run** `cd ios/MCCore && swift test` — Expected: FAIL (компиляция).
- [ ] **Step 3: Implement** модели (даты — `APIDate`), подписи, группу. `patch_fixtures.py`: подставить ключ `sanctions` в фикстуры из `MockShipmentSource` + `project_shipment` (импорт `app`, как уже сделано для сегментов), остальные значения не менять; запустить `python3 ios/scripts/patch_fixtures.py`.
- [ ] **Step 4: Run** `swift test` — Expected: PASS (все существующие + новые).
- [ ] **Step 5: Commit** `git commit -m "iOS: модели и подписи проверки санкций, фикстуры"`

---

### Task 6: iOS — правило уведомления о санкциях

**Files:**
- Modify: `ios/MCCore/Sources/MCCore/NotificationRules.swift`, `ios/MCCore/Sources/MCCore/TrackedShipments.swift`, `ios/MCCore/Sources/MCCore/Strings.swift`
- Test: `ios/MCCore/Tests/MCCoreTests/NotificationRulesTests.swift`, `TrackedShipmentsTests.swift`

**Interfaces:**
- Consumes: Task 5
- Produces:
  - `NoticeKind.sanctions`; `NotifySettings.sanctions: Bool` (init с пятым параметром, `.all` — все `true`)
  - `NotificationRules.sanctions(_ shipments: [Shipment], sent: Set<String>, settings: NotifySettings, labels: Labels) -> [AppNotice]` — `id` = `sanctions-<ref>-<status>-<сильные совпадения как listId:hsCode, отсортированные, через запятую>`
  - `merge`: приоритет `.sanctions` = 0 (выше `.storm`)
  - `TrackedShipments.onAdded: (@MainActor (Shipment) -> Void)?` — вызывается в `add` после сохранения
  - строки `notice.sanctions.flagged.title/body`, `notice.sanctions.missing.title/body`, `notice.sanctions.more` («и ещё {n}») RU/EN

- [ ] **Step 1: Write the failing tests:**

```swift
func test_sanctions_flagged_notifies_withoutOldState()
func test_sanctions_sentSet_blocksRepeat_withoutOldState()   // тот же id в sent → []
func test_sanctions_newStrongMatch_newId()
func test_sanctions_review_and_clear_silent()
func test_sanctions_missing_notifies()
func test_sanctions_settingOff_silent()
func test_sanctions_one_notice_per_shipment()               // две сильные позиции → одно уведомление, body с «и ещё 1»
func test_merge_sanctionsOnTopOfStorm()
func test_add_callsOnAdded()                                 // TrackedShipmentsTests
```

Ожидаемые тексты (RU): заголовок `"MC-26-0431: возможна санкционка"`; тело начинается с `labels.sanctionsMatch(первое сильное)` и кончается `"Проверьте вручную."`; `missing`: `"MC-26-0447: прошёл границу Казахстана без пакинг-листа"` / `"Проверить на санкции нельзя — запросите пакинг-лист до Актау."`.

- [ ] **Step 2: Run** `swift test` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `swift test` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "iOS: уведомление о санкциях — по состоянию и набору отправленных"`

---

### Task 7: iOS — приложение: настройки, карточка, список, смоук

**Files:**
- Modify: `ios/App/Notify/Notifier.swift` (`NotifyPrefs`: ключ `sanctions`, набор отправленных `mc.notify.sanctions.sent` — `loadSent()`/`recordSent(_:)`)
- Modify: `ios/App/AppModel.swift` (`handle(_:)` и `observe(_:)`: `onAdded` → правило санкций для одного груза)
- Create: `ios/App/Views/SanctionsSection.swift`
- Modify: `ios/App/Views/ShipmentDetailView.swift` (секция после `DelaySection`), `ios/App/Views/ShipmentRow.swift` (пометка «Санкции?» при `flagged`/`missing`), `ios/App/Localizable.xcstrings` (`notify.sanctions`, `card.sanctions`, `card.sanctions.disclaimer`, `card.sanctions.asOf`, `row.sanctions`)
- Test: `ios/UITests/SmokeTests.swift`

**Interfaces:**
- Consumes: Tasks 5–6
- Produces: `accessibilityIdentifier`: `notify.sanctions` (уже даёт `NotifyToggle`), `card.sanctions`, `row.sanctions`

- [ ] **Step 1: Write the failing UI test** `test_sanctionsCardAndRow` (`-mc-fake-api`): добавить MC-26-0431 → в строке `row.sanctions` существует; карточка → `card.sanctions` содержит «возможна» и «подсказка»; скриншот `13-sanctions-card-ru`. В `test_notificationSettings` — список id дополнить `notify.sanctions`.
- [ ] **Step 2: Run** `xcodebuild test -scheme MiddleCorridor -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:MiddleCorridorUITests/SmokeTests/test_sanctionsCardAndRow` — Expected: FAIL.
- [ ] **Step 3: Implement.** Секция: статус (`labels.sanctionsStatus`), совпадения (сильные — `Theme.critical`, слабые — `.secondary`), списки с «актуально на», дисклеймер. `pending` — «Ждём пакинг-лист», `clear` — «Совпадений нет».
- [ ] **Step 4: Run** UI-смоук целиком — Expected: PASS; посмотреть скриншоты RU/EN, светлая/тёмная.
- [ ] **Step 5: Commit** `git commit -m "iOS: блок «Проверка санкций», пометка в списке, переключатель уведомления"`

---

### Task 8: Документация и сквозная проверка

**Files:**
- Modify: `CLAUDE.md` (грабли: списки — данные с источником, КН-8 по 6 знакам, флаг ≠ вердикт, лист не отдаётся целиком, санкции — уведомление по состоянию), `docs/IOS.md` (вид уведомления)
- Modify (если понадобится): `vercel.json` (`functions["api/index.py"].includeFiles: "app/data/**"`)

- [ ] **Step 1:** `.venv/bin/python -m pytest -q`, `ruff check .`, `black --check .`, `cd ios/MCCore && swift test` — всё зелёное.
- [ ] **Step 2:** Симулятор против локального мока (`MOCK_DATA=true .venv/bin/python -m app.main`, сервер в скрытых настройках `http://localhost:8000`): добавить MC-26-0431 → баннер «возможна санкционка»; MC-26-0412 → блок «проверить вручную», баннера нет; перезапуск → повтора нет.
- [ ] **Step 3:** После пуша ветки — превью Vercel: `GET <preview>/api/v1/shipments/MC-26-0431` → `sanctions.status == "flagged"`. Если `sanctions` пуст/ошибка из-за отсутствия CSV — добавить `includeFiles` и повторить.
- [ ] **Step 4: Commit** `git commit -m "Санкции: документация"`
