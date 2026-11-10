# Аккаунты, доступ, грузы в базе и события на чекпоинтах — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** экспедитор и его агенты на узлах ведут реальные грузы в iOS-приложении: вход по коду из
письма, права по компании и узлу, грузы и события в Postgres, проекция тем же `project_shipment`,
push и e-mail подписчикам.

**Architecture:** новые таблицы (Alembic) + сервисы без FastAPI (`services/accounts/…`) + роуты
`/api/v1/auth|me|my|admin` с зависимостью «текущий пользователь» + CLI для платформа-админа. Грузы из
базы превращаются в `ShipmentPlan` (`DbShipmentSource`) и проецируются как демо. iOS получает второй
клиент (`AccountAPI`) с токеном из Keychain.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, pydantic v2, httpx (APNs по HTTP/2,
письма по HTTPS), pytest на SQLite; Swift 6 / SwiftUI, MCCore, XCTest.

**Spec:** `docs/superpowers/specs/2026-11-10-accounts-and-checkpoints-design.md`

## Global Constraints

- Слои: `services/` не импортирует fastapi/aiogram; запросы к БД — только в `db/repositories/`.
- Enum'ы в БД — VARCHAR (`_str_enum`, `native_enum=False`). Новая колонка без миграции = красный CI
  (`alembic check`); миграция обязана откатываться.
- Секреты — только ENV (`app/config.py`); `.env` не коммитить и не печатать.
- Коды входа — HMAC-SHA256 с `AUTH_SECRET`; токены сессий — 32 байта `secrets.token_urlsafe(32)`,
  в базе SHA-256; сравнение — `hmac.compare_digest`.
- Сроки: код — 10 мин, 5 попыток; приглашение — 7 дней; сессия — 60 дней (скользящее
  `last_used_at`, жёсткий `expires_at`).
- Лимиты: 3 письма с кодом за 15 мин на e-mail, 20 запросов кода за час на IP; счётчики — в Postgres
  (строки `login_codes`), не в памяти.
- `POST /auth/code` — всегда `202` с одинаковым телом.
- Нет доступа к грузу/компании — `404`, не `403`.
- Коды стоянок (`hold_code`): `weather_ban` | `customs_wait` | `ferry_loading_wait` | `other`
  (`other` → `hold_code=None`, причина — текст примечания).
- Эндпоинты аккаунтов при `MOCK_DATA=true` или без `AUTH_SECRET` → `404` (Vercel их не обслуживает).
- Публичный `/api/v1/snapshot` и `/api/v1/shipments/{ref}` реальных грузов не отдают никогда.
- В логах — id пользователя/груза, не e-mail и не токен; в push — номер груза и событие, без
  содержимого контейнера и санкционного статуса.
- `requirements.txt` — зеркало pyproject (тест `test_requirements_mirror_pyproject`).
- iOS: токен — только Keychain; тексты — `Localizable.xcstrings` через `L10n` (RU/EN); новые поля
  `/api/v1` — в `Models.swift` и фикстурах. Перед коммитом: `ruff check --fix . && black .`, `pytest -q`;
  iOS — `swift test` в `ios/MCCore` и UI-смоук на iPhone 13 Pro Max
  (`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`).

## Review Focus

1. **E-mail в разном регистре и с пробелами** (`" Agent@Firm.KZ "`) — один и тот же пользователь,
   приглашение принимается. Тест — Task 2 `test_email_normalized_everywhere`.
2. **Человек в двух компаниях с разными ролями** (агент Актау у X, viewer у Y) — видит грузы обеих
   по своим правам, событие у Y отметить не может. Тест — Task 3 `test_two_memberships_rights_do_not_mix`.
3. **Исправление события, которое само было исправлено** (цепочка supersedes) и исправление события
   чужого груза — проекция берёт только «живые» события; чужой `supersedes_id` → 422. Тест — Task 6
   `test_superseded_chain_and_foreign_supersedes`.
4. **Правка маршрута, отрезающая узел, на котором уже есть событие**, или делающая несуществующее
   плечо — 422, груз не меняется, ревизия не пишется. Тест — Task 5 `test_route_edit_keeps_passed_part`.
5. **Отозванный агент с живой сессией** — следующий запрос по его токену видит только то, что
   осталось по другим членствам; отключённый пользователь (`disabled_at`) — 401. Тест — Task 8
   `test_revoked_membership_and_disabled_user`.

---

### Task 1: Настройки, модели, миграция

**Files:**
- Modify: `app/config.py`, `.env.example`, `app/db/models.py`
- Create: `alembic/versions/<rev>_accounts_and_shipments.py`
- Test: `tests/test_models.py`, `tests/test_config.py`

**Interfaces:**
- Produces (Settings): `auth_secret: str = ""`, `accounts_enabled` (property: `bool(auth_secret) and
  not mock_data`), `email_provider: str = "log"` (`log` | `resend`), `email_api_key: str = ""`,
  `email_from: str = ""`, `apns_key_id`, `apns_team_id`, `apns_key_p8` (строка PEM),
  `apns_bundle_id: str = "com.middlecorridor.app"` (сверить с `ios/project.yml`), `apns_env:
  str = "sandbox"`, `shipment_ref_prefix: str = "MC"`.
- Produces (модели, `app/db/models.py`, все `created_at` — `server_default=func.now()`):
  `Organization(id, name, kind: OrgKind{forwarder,client,platform})`,
  `User(id, email unique, name, locale, is_platform_admin, last_login_at, disabled_at)`,
  `Membership(id, user_id, org_id, role: Role{owner,admin,agent,viewer}, node_codes: JSON list[str],
  unique(user_id, org_id))`,
  `Invitation(id, org_id, email, role, node_codes, invited_by, expires_at, accepted_at, revoked_at)`,
  `LoginCode(id, email, ip, code_hash, expires_at, attempts, used_at)` (индексы по `(email, created_at)`,
  `(ip, created_at)`),
  `AuthSession(id, user_id, token_hash unique, last_used_at, expires_at, device_name, revoked_at)`,
  `OrgLink(forwarder_id, client_id)` (PK пара),
  `ShipmentRow(id, ref unique, org_id, container_no, container_type, route: JSON list[str],
  planned_departure_at, cargo, cargo_en, cargo_manifest: JSON|None, created_by, archived_at)`,
  `ShipmentShare(shipment_id, org_id)` (PK пара),
  `ShipmentEventRow(id, shipment_id, kind: CheckpointEventKind{arrived,departed,held,released},
  node_code, occurred_at, hold_code, note, vessel, source="manual", created_by, supersedes_id)`,
  `ShipmentRevision(id, shipment_id, changed_by, at, before: JSON, after: JSON)`,
  `Subscription(user_id, shipment_id, push, email, muted_at)` (PK пара),
  `Device(id, user_id, apns_token unique, environment, revoked_at)`,
  `AuditLog(id, user_id|None, action, entity, entity_id, at, ip, details: JSON)`.
  Имена таблиц — как в спеке (`organizations`, `users`, `memberships`, `invitations`, `login_codes`,
  `sessions`, `org_links`, `shipments`, `shipment_shares`, `shipment_events`, `shipment_revisions`,
  `subscriptions`, `devices`, `audit_log`). Класс груза — `ShipmentRow`, чтобы не путать с pydantic
  `tracking.Shipment`.

- [ ] **Step 1:** тесты: `test_accounts_enabled_needs_secret_and_real_mode` (пусто → False;
  секрет + `mock_data=True` → False; секрет + боевой → True) и в `test_models.py`
  `test_account_tables_roundtrip` — создать организацию, пользователя, членство агента с
  `node_codes=["AKTAU"]`, груз с маршрутом и событие; прочитать обратно; повторное членство той же
  пары → `IntegrityError`.
- [ ] **Step 2:** `pytest tests/test_models.py tests/test_config.py -q` → FAIL (нет моделей/поля).
- [ ] **Step 3:** модели и настройки; переменные с комментариями — в `.env.example` (значения пустые).
- [ ] **Step 4:** миграция `alembic revision --autogenerate -m "accounts and shipments"` на Postgres
  :5433 (или песочничный); проверить `alembic upgrade head && alembic downgrade -1 && alembic upgrade
  head && alembic check` → «No new upgrade operations detected».
- [ ] **Step 5:** `pytest -q` → PASS; ruff/black; коммит `Аккаунты: таблицы и настройки`.

### Task 2: Вход — коды, сессии, лимиты

**Files:**
- Create: `app/services/accounts/__init__.py`, `app/services/accounts/auth.py`,
  `app/services/accounts/security.py`, `app/services/accounts/mail.py`,
  `app/db/repositories/accounts.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces `security.py`: `normalize_email(raw: str) -> str` (strip + lower; без «@» → `ValueError`),
  `hash_code(secret: str, email: str, code: str) -> str` (HMAC-SHA256 hex по `email:code`),
  `new_code() -> str` (6 цифр, `secrets.randbelow`), `new_token() -> str`, `hash_token(token) -> str`
  (SHA-256 hex).
- Produces `mail.py`: `class EmailSender(Protocol): async def send(self, to: str, subject: str, text:
  str) -> None`; `LogEmailSender` (пишет в structlog только `to_hash`/subject — тело с кодом не логирует;
  хранит отправленное в `self.sent` для тестов); `ResendEmailSender(api_key, sender, client:
  httpx.AsyncClient)` — POST `https://api.resend.com/emails`; тексты писем RU/EN — словарь в `mail.py`
  (`login_code`, `invited`), язык — `User.locale` или `ru`.
- Produces `auth.py`: `class AuthService(session_factory, settings, mail: EmailSender, clock:
  Callable[[], datetime])` с методами
  `async request_code(email: str, ip: str) -> None` (всегда без ошибки наружу; письмо — только если
  e-mail есть в `users` без `disabled_at` или в неистёкших неотозванных `invitations`; лимиты из
  Global Constraints; превышение — тихо не шлёт),
  `async verify(email: str, code: str, device_name: str, ip: str) -> tuple[str, User] | None`
  (последний неиспользованный неистёкший код; `attempts += 1` до сравнения; ≥5 → None; успех → `used_at`,
  принять приглашения: создать `User` при отсутствии, `Membership` на каждое приглашение (если уже есть
  членство в той же компании — обновить роль/узлы), `accepted_at`; создать `AuthSession`; вернуть
  открытый токен один раз),
  `async authenticate(token: str) -> User | None` (сессия не отозвана, не истекла, пользователь не
  отключён; обновить `last_used_at` не чаще раза в 5 мин),
  `async logout(token: str) -> None`.
  Каждое значимое действие пишет `AuditLog` (`login.code_sent`, `login.ok`, `login.failed`,
  `invitation.accepted`, `logout`) — через `repositories.accounts.audit(...)`.

- [ ] **Step 1:** тесты (фейковые часы, `LogEmailSender`):
  `test_unknown_email_gets_no_mail_but_same_result`, `test_code_flow_issues_token_once`
  (токен в базе не хранится открыто: `hash_token(token)` == `token_hash`),
  `test_code_expires_after_10_min`, `test_five_wrong_attempts_burn_code`,
  `test_rate_limit_email_3_per_15_min`, `test_rate_limit_ip_20_per_hour`,
  `test_invitation_accepted_on_verify_creates_user_and_membership`,
  `test_expired_or_revoked_invitation_ignored`, `test_logout_revokes`, `test_session_expires_60_days`,
  `test_disabled_user_cannot_login_or_authenticate`, `test_email_normalized_everywhere` (Review Focus 1),
  `test_mail_log_has_no_code` (в выводе structlog нет ни кода, ни адреса).
- [ ] **Step 2:** `pytest tests/test_auth.py -q` → FAIL.
- [ ] **Step 3:** реализация по интерфейсам.
- [ ] **Step 4:** `pytest -q` → PASS.
- [ ] **Step 5:** коммит `Аккаунты: вход по коду из письма, сессии, лимиты`.

### Task 3: Права

**Files:**
- Create: `app/services/accounts/access.py`
- Modify: `app/db/repositories/accounts.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Consumes: модели Task 1.
- Produces: `@dataclass(frozen=True) class Principal(user_id: int, is_platform_admin: bool,
  memberships: tuple[MembershipView, ...])`, `MembershipView(org_id, org_kind, role, node_codes:
  frozenset[str])`; `async load_principal(session, user: User) -> Principal`;
  чистые функции над `Principal` и `ShipmentAccess(org_id, route: tuple[str, ...], shared_org_ids:
  frozenset[int])`:
  `can_view(p, s) -> bool`, `can_manage(p, s) -> bool` (owner/admin компании-владельца или
  платформа), `event_nodes(p, s) -> frozenset[str]` (узлы, где можно отмечать: manage → весь маршрут;
  agent → пересечение `node_codes` (пусто = весь маршрут) с маршрутом; иначе пусто),
  `can_invite(p, org_id) -> bool`, `can_share_with(p, s, client_org_id, linked: set[int]) -> bool`,
  `creatable_orgs(p) -> list[int]` (компании-экспедиторы, где owner/admin);
  `async visible_shipment_ids(session, p) -> list[int]` — одним запросом: свои компании (агенту —
  только где маршрут содержит его узел, фильтр в Python после выборки по org) ∪ `shipment_shares`
  компаний пользователя; платформа — все; архивные исключены.

- [ ] **Step 1:** таблица-матрица `@pytest.mark.parametrize` роль × действие (`view`, `manage`,
  `event@AKTAU`, `event@POTI`, `invite`, `share`) для: платформа, owner X, admin X, agent X [AKTAU],
  agent X [] (все узлы), viewer клиента Y с шарингом, viewer Y без шаринга, owner чужого экспедитора Z;
  плюс `test_agent_sees_only_routes_with_his_node`, `test_archived_hidden`,
  `test_two_memberships_rights_do_not_mix` (Review Focus 2).
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** PASS.
- [ ] **Step 5:** коммит `Аккаунты: права по компании и узлу`.

### Task 4: Компании, приглашения, CLI

**Files:**
- Create: `app/services/accounts/orgs.py`, `app/cli.py`
- Test: `tests/test_orgs.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Principal`, `can_invite` (Task 3), `EmailSender` (Task 2).
- Produces: `class OrgService(session_factory, mail, clock)`:
  `create_org(actor: Principal | None, name, kind) -> Organization` (только платформа; `actor=None` —
  CLI), `link(actor, forwarder_id, client_id)` (только платформа; forwarder-kind и client-kind, иначе
  `ValueError`), `invite(actor, org_id, email, role, node_codes) -> Invitation` (owner/admin своей
  компании или платформа; `agent` с узлами только из `corridor.NODES`; роль `owner` — только
  платформа; повторное приглашение того же e-mail в ту же компанию отзывает прежнее; письмо
  `invited`), `revoke_membership(actor, org_id, user_id)`, `members(actor, org_id)`,
  `linked_clients(actor, forwarder_id) -> list[Organization]`, `set_platform_admin(email)`;
  ошибки прав — `PermissionDenied` (наружу → 404), данных — `ValueError` (→ 422).
- Produces CLI (`python -m app.cli`): `admin --email E`, `org create --kind K --name N` (печатает id),
  `org link --forwarder ID --client ID`, `invite --org ID --email E --role R [--nodes AKTAU,POTI]`,
  `user disable --email E`. Использует `get_settings().database_url`; e-mail не печатает целиком.

- [ ] **Step 1:** тесты: `test_only_platform_creates_orgs_and_links`,
  `test_forwarder_admin_invites_agent_with_nodes`, `test_unknown_node_rejected`,
  `test_owner_role_only_by_platform`, `test_reinvite_revokes_previous`,
  `test_linked_clients_only_own`, `test_cli_bootstrap` (в `test_cli.py` вызвать `main([...])` с
  SQLite-URL временного файла: admin → org create → invite; в базе приглашение есть).
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** PASS.
- [ ] **Step 5:** коммит `Аккаунты: компании, связи, приглашения, команды админа`.

### Task 5: Грузы в базе — создание, правка, шаринг, проекция

**Files:**
- Create: `app/services/schedule.py`, `app/services/accounts/shipments.py`,
  `app/services/accounts/db_source.py`
- Modify: `app/integrations/mock/fleet.py` (использует `schedule.plan_legs`), `app/db/repositories/accounts.py`
- Test: `tests/test_schedule.py`, `tests/test_account_shipments.py`

**Interfaces:**
- Produces `schedule.py`: `DWELL_H` (перенос `_DWELL_H` из мока), `validate_route(route: list[str])
  -> None` (≥2 узлов, без повторов, каждая пара — `corridor.segment` без исключения, иначе
  `ValueError` с кодом узлов), `plan_legs(route, departure: datetime, vessels=None) ->
  tuple[PlannedLeg, ...]` (та же раскладка, что в `build_plan`; мок переводится на неё без изменения
  результатов — существующие тесты мока остаются зелёными).
- Produces `shipments.py`: `iso6346_valid(no: str) -> bool` (4 буквы + 7 цифр, контрольная цифра;
  `DEMU5010012` из мока проходить не обязан — это не тест), `class ShipmentService(session_factory,
  clock)`: `create(actor, *, org_id, container_no, container_type, route, planned_departure_at,
  cargo, cargo_en=None) -> ShipmentRow` (ref `"{prefix}-{YY}-{NNNN}"`, NNNN — следующий в году по
  префиксу, уникальность защищена ограничением + одна повторная попытка; создатель и все
  owner/admin компании — подписчики), `update(actor, ref, **changes) -> ShipmentRow` (поля:
  `container_no`, `container_type`, `cargo`, `cargo_en`, `planned_departure_at`, `route`; маршрут —
  префикс до последнего узла с живым событием обязан сохраниться, хвост проходит
  `validate_route`; пишет `ShipmentRevision(before, after)` только изменённых полей; возвращает
  `tuple[ShipmentRow, bool]` — второй элемент `route_changed`, по нему Task 8 зовёт
  `ShipmentNotifier.on_route_changed`), `share(actor, ref, client_org_id)` (через `can_share_with` + `org_links`; viewers клиента —
  подписчики), `archive(actor, ref)`, `get(actor, ref) -> ShipmentRow` (нет прав → `NotFound`),
  `list_for(actor) -> list[ShipmentRow]`.
- Produces `db_source.py`: `class DbShipmentSource(session_factory, principal: Principal | None)`
  реализует `ShipmentSource.list_plans(at)` → `ShipmentPlan` на каждый видимый груз:
  `legs=plan_legs(route, planned_departure_at)`, `events` из живых событий (`arrived`/`departed` →
  `TrackingEvent`, `note_vessel=vessel`, `note_code="loaded_on_vessel"` если указан vessel на
  `departed`), открытая стоянка (`held` без последующего `released` на том же узле и без отправления
  оттуда) → `hold_code`/`hold_node`/`hold_reason` (для `other` — `hold_code=None`, `hold_reason=note`);
  `client` — имя компании-владельца; `cargo_manifest` из JSON. События с `occurred_at > at` не
  учитываются (replay).

- [ ] **Step 1:** тесты `test_schedule.py`: `test_plan_legs_matches_mock_build_plan` (для
  `ROUTE_KOSTANAY` то же расписание, что у мок-плана с тем же стартом),
  `test_validate_route_rejects_gap_and_repeat`.
  `test_account_shipments.py`: `test_iso6346` (`CSQU3054383` — валиден, пример из стандарта;
  `CSQU3054384`, `CSQU305438`, `1SQU3054383` — нет; строчные и пробелы нормализуются), `test_create_assigns_ref_and_subscribes`,
  `test_agent_cannot_create`, `test_update_writes_revision_only_changed`,
  `test_route_edit_keeps_passed_part` (Review Focus 4), `test_share_only_linked_client`,
  `test_projection_from_db_events_and_hold` (событие «убыл из Поти», «стоит в Баку: weather_ban» →
  `project_shipment` даёт `state=waiting`, `hold_code="weather_ban"`, `hold_node="BAKU_ALAT"`),
  `test_projection_replay_ignores_future_events`.
- [ ] **Step 2:** FAIL → **Step 3:** реализация (сначала `schedule.py` и перевод мока, `pytest -q`
  зелёный, потом сервисы) → **Step 4:** PASS всё.
- [ ] **Step 5:** коммит `Грузы в базе: создание, правка с историей, шаринг, проекция`.

### Task 6: События на чекпоинтах

**Files:**
- Create: `app/services/accounts/events.py`
- Test: `tests/test_checkpoint_events.py`

**Interfaces:**
- Consumes: `event_nodes` (Task 3), `ShipmentService.get` (Task 5).
- Produces: `class EventService(session_factory, clock, on_event: Callable[[ShipmentEventRow,
  ShipmentRow, int], Awaitable[None]] | None)`:
  `add(actor, ref, *, kind, node_code, occurred_at=None, hold_code=None, note=None, vessel=None,
  supersedes_id=None) -> ShipmentEventRow`. Правила (нарушение → `ValueError` с кодом причины для
  422): узел в маршруте и в `event_nodes` (иначе `NotFound` → 404, если груз не виден вовсе;
  `node_not_allowed` если виден, но узел чужой); `occurred_at` по умолчанию сейчас, не позже
  `now + 5 мин`, не раньше последнего живого события груза (`out_of_order`) — кроме исправления,
  которое проверяется относительно события перед исправляемым; `held` требует `hold_code` из
  списка; `released` требует открытой стоянки на этом узле; `supersedes_id` — живое событие этого же
  груза (иначе `bad_supersedes`); `note` ≤ 500 символов, `vessel` ≤ 64. Аудит `event.add`. После
  коммита — `on_event(event, shipment, actor.user_id)`.
  `list(actor, ref) -> list[ShipmentEventRow]` — все, с пометкой `superseded`.

- [ ] **Step 1:** тесты: `test_agent_marks_own_node_only`, `test_viewer_cannot_mark`,
  `test_time_not_future_not_before_previous`, `test_held_needs_code_released_needs_hold`,
  `test_correction_replaces_in_projection`, `test_superseded_chain_and_foreign_supersedes`
  (Review Focus 3), `test_on_event_called_after_commit_with_author`.
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** PASS.
- [ ] **Step 5:** коммит `События на чекпоинтах: прибыл, убыл, стоянка, исправления`.

### Task 7: Уведомления — push и e-mail

**Files:**
- Create: `app/services/accounts/notify.py`, `app/integrations/apns.py`
- Modify: `app/services/accounts/mail.py` (текст `event`), `pyproject.toml` + `requirements.txt`
  (`httpx[http2]`, `pyjwt[crypto]`)
- Test: `tests/test_account_notify.py`, `tests/test_apns.py`

**Interfaces:**
- Produces `notify.py`: `class PushSender(Protocol): async def send(self, token: str, env: str,
  title: str, body: str, data: dict[str, str]) -> PushResult` (`ok` | `gone` | `error`);
  `LogPushSender`; `class ShipmentNotifier(session_factory, push: PushSender, mail: EmailSender)` с
  `async on_event(event, shipment, author_id)` и `async on_route_changed(shipment, author_id)`:
  получатели — подписчики без `muted_at`, у кого сейчас есть `can_view`, кроме автора; push на все
  неотозванные устройства (`gone` → `revoked_at`), e-mail если `subscription.email`; текст
  `event_text(kind, node_code, hold_code, lang) -> str`: «{ref}: прибыл в {узел}» / «убыл из {узел}» /
  «стоит в {узел} — {причина}» / «снят со стоянки в {узел}» (EN — Arrived at / Departed / Held at — /
  Released at); `data={"ref": ref}`. Отправка — `asyncio.create_task` с одной повторной попыткой
  через 30 с; исключения логируются, не роняют запрос.
  `async register_device(user_id, token, env)` (повторный токен другого пользователя —
  переназначить), `async set_subscription(actor, ref, push, email, muted)`.
- Produces `apns.py`: `ApnsSender(key_id, team_id, key_p8, bundle_id, client)` — JWT ES256
  (кэш 50 мин), POST `https://api{.sandbox}.push.apple.com/3/device/{token}`, `apns-topic`,
  `apns-push-type: alert`; 410 / `BadDeviceToken` → `gone`.
- Выбор отправителей — в `main` (Task 8): ключи APNs заданы → `ApnsSender`, иначе `LogPushSender`;
  `email_provider=resend` → `ResendEmailSender`.

- [ ] **Step 1:** тесты: `test_author_not_notified`, `test_only_viewers_with_access`
  (отозванный шаринг → не получает), `test_muted_skipped`, `test_gone_token_revoked`,
  `test_push_body_has_no_cargo_or_sanctions`, `test_event_text_ru_en` (4 вида × 2 языка);
  `test_apns.py` — `httpx.MockTransport`: заголовки `authorization: bearer …`, `apns-topic`, путь;
  410 → `gone`.
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** PASS; `test_requirements_mirror_pyproject`
  зелёный.
- [ ] **Step 5:** коммит `Уведомления о событиях: push (APNs) и e-mail`.

### Task 8: API аккаунтов

**Files:**
- Create: `app/api/routes/accounts.py`, `app/api/deps.py`
- Modify: `app/api/main.py` (роутер, CORS `GET, POST, PATCH, DELETE` + `Authorization`, лимит тела
  64 КБ для `/api/v1/auth|me|my|admin`), `app/main.py` (сборка сервисов в `app.state.accounts` при
  `settings.accounts_enabled`), `api/index.py` не трогать (Vercel без `AUTH_SECRET` → 404)
- Test: `tests/test_accounts_api.py`

**Interfaces:**
- Consumes: сервисы Tasks 2–7.
- Produces `deps.py`: `accounts(request) -> AccountsServices` (нет — `HTTPException(404)`),
  `current_principal(request, authorization: Header) -> Principal` (нет/плохой токен → 401 с
  `WWW-Authenticate: Bearer`), `client_ip(request)` (первый адрес `X-Forwarded-For` только если
  `settings.trust_proxy`, иначе `request.client.host`; добавить `trust_proxy: bool = False` в Settings).
- Produces роуты (pydantic-схемы ответов рядом в `accounts.py`; ошибки `PermissionDenied`/`NotFound`
  → 404, `ValueError(code)` → 422 `{"detail": code}`):
  `POST /api/v1/auth/code {email}` → 202 `{"status":"sent"}`;
  `POST /api/v1/auth/verify {email, code, device_name}` → 200 `{token, me}` | 401;
  `POST /api/v1/auth/logout` → 204; `GET /api/v1/me` → `{id, email, name, locale,
  is_platform_admin, memberships: [{org_id, org_name, org_kind, role, node_codes}]}`;
  `PATCH /api/v1/me {name?, locale?}`; `POST /api/v1/me/devices {apns_token, environment}` → 204;
  `GET /api/v1/orgs/{id}/members`, `POST /api/v1/orgs/{id}/invitations`,
  `DELETE /api/v1/orgs/{id}/members/{user_id}`, `GET /api/v1/orgs/{id}/clients`;
  `POST /api/v1/admin/orgs`, `POST /api/v1/admin/orgs/{id}/links {client_id}`,
  `POST /api/v1/admin/orgs/{id}/invitations` (только платформа);
  `GET /api/v1/my/shipments` → `list[MyShipment]`, где `MyShipment = {shipment: Shipment (tracking),
  org_id, can_manage, event_nodes: list[str], container_no}`;
  `POST /api/v1/my/shipments`, `GET|PATCH /api/v1/my/shipments/{ref}`,
  `POST /api/v1/my/shipments/{ref}/share {org_id}`, `POST …/{ref}/archive`,
  `GET|POST /api/v1/my/shipments/{ref}/events`, `PUT /api/v1/my/shipments/{ref}/subscription`.
  Проекция — `project_shipment(plan, now)` из `DbShipmentSource(principal)`; `cargo_details` и
  санкции — как у публичного груза.

- [ ] **Step 1:** тесты через `httpx.AsyncClient(transport=ASGITransport(app))` с SQLite и
  `LogEmailSender` (код берётся из `sent`): `test_accounts_404_in_mock_mode`,
  `test_full_flow_invite_login_create_event_notify` (админ CLI-сервисом создаёт компанию и
  приглашение → вход → создание груза → агент входит и отмечает «прибыл в Актау» → у владельца в
  `LogPushSender`/почте уведомление), `test_no_token_401_foreign_ref_404`,
  `test_code_endpoint_same_response_for_unknown`, `test_body_size_limit_413`,
  `test_public_snapshot_has_no_real_shipments` (созданный в базе ref отсутствует в `/snapshot` и
  `/shipments/{ref}` → 404), `test_revoked_membership_and_disabled_user` (Review Focus 5),
  `test_cors_allows_authorization_header`.
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** `pytest -q` и `--cov` (порог
  pyproject) → PASS.
- [ ] **Step 5:** коммит `API аккаунтов: вход, компании, мои грузы, события`. Push ветки, PR,
  дождаться зелёного CI (backend · postgres · web) — промежуточный PR вливается после зелёного CI.

### Task 9: MCCore — клиент аккаунта

**Files:**
- Create: `ios/MCCore/Sources/MCCore/AccountAPI.swift`, `ios/MCCore/Sources/MCCore/AccountModels.swift`,
  `ios/MCCore/Sources/MCCore/TokenStore.swift`, `ios/MCCore/Sources/MCCore/ContainerNumber.swift`
- Modify: `ios/MCCore/Sources/MCCore/Labels.swift` + `Strings.swift` (`event.held`, `event.released`,
  коды стоянок для формы), `NotificationRules.swift` (флаг «грузы аккаунта — push»)
- Test: `ios/MCCore/Tests/MCCoreTests/AccountTests.swift`

**Interfaces:**
- Produces: `public protocol TokenStore: Sendable { func load() -> String?; func save(_: String?) }`,
  `InMemoryTokenStore`; модели `Me`, `MembershipInfo`, `MyShipment(shipment: Shipment, orgId,
  canManage, eventNodes, containerNo)`, `NewShipment`, `ShipmentPatch`, `CheckpointEventInput(kind:
  CheckpointKind{arrived,departed,held,released}, nodeCode, occurredAt: Date?, holdCode: String?,
  note, vessel, supersedesId)`, `CheckpointEventRecord`, `Invitation`, `OrgMember`, `OrgSummary`;
  `public protocol AccountAPI: Sendable` с методами по одному на эндпоинт Task 8
  (`requestCode`, `verify`, `logout`, `me`, `registerDevice`, `myShipments`, `create`, `update`,
  `addEvent`, `events`, `share`, `archive`, `members`, `invite`, `revoke`, `clients`);
  `HTTPAccountAPI(baseURL:, tokens: TokenStore, session:)` — `Authorization: Bearer`, 401 → стирает
  токен и бросает `APIError.unauthorized` (новый case), 422 → `APIError.rejected(code)` (новый case);
  даты — `APIDate`. `ContainerNumber.isValid(_:)` — тот же ISO 6346, что сервер.
  `NotificationRules`: грузы из аккаунта при `pushRegistered == true` в diff не участвуют.
- [ ] **Step 1:** тесты: кодирование/декодирование моделей на JSON-фикстуре из ответа Task 8
  (сгенерировать скриптом в `ios/scripts/` по аналогии с `patch_fixtures.py`), заголовок Bearer через
  `URLProtocol`-заглушку, 401 стирает токен, 422 → `rejected("node_not_allowed")`,
  `ContainerNumber` (те же примеры, что в Task 5), правило уведомлений.
- [ ] **Step 2:** `cd ios/MCCore && swift test` → FAIL → **Step 3:** реализация → **Step 4:** PASS.
- [ ] **Step 5:** коммит `iOS: клиент аккаунта в MCCore`.

### Task 10: iOS — вход и «Мои грузы» с сервера

**Files:**
- Create: `ios/App/Account/KeychainTokenStore.swift`, `ios/App/Account/AccountModel.swift`,
  `ios/App/Account/LoginView.swift`, `ios/App/Fake/FakeAccountAPI.swift`
- Modify: `ios/App/Views/SettingsView.swift` («Войти»/аккаунт/«Выйти»), `ios/App/Views/MyShipmentsView.swift`
  (секции по срочности объединяют локальные и аккаунтные; у аккаунтных — бейдж компании),
  `ios/App/Views/ShipmentDetailView.swift` (источник аккаунтного груза — `AccountModel`),
  `ios/App/AppModel.swift`, `ios/project.yml` (ключ `MC_ACCOUNT_API_URL` в Info.plist),
  `ios/App/Localizable.xcstrings`
- Test: `ios/UITests/SmokeTests.swift`

**Interfaces:**
- Consumes: `AccountAPI`, `TokenStore` (Task 9).
- Produces: `@Observable final class AccountModel(api: any AccountAPI, tokens: any TokenStore)` —
  `me: Me?`, `shipments: [MyShipment]`, `func requestCode(email:)`, `func verify(email:code:)`,
  `func refresh()` (раз в минуту на переднем плане, как демо), `func logout()`; при `unauthorized` —
  выход без падения. `-mc-fake-api` подставляет `FakeAccountAPI` (код `000000`, один экспедитор с
  двумя грузами, агент Актау).
- [ ] **Step 1:** UI-тест `test_loginAndAccountShipments`: Настройки → «Войти» → e-mail → код
  `000000` → в «Мои грузы» появились два аккаунтных груза; «Выйти» → исчезли.
- [ ] **Step 2:** FAIL → **Step 3:** реализация (`xcodegen generate`) → **Step 4:** смоук целиком
  на iPhone 13 Pro Max PASS (`-mc.splash NO`).
- [ ] **Step 5:** коммит `iOS: вход по коду и грузы аккаунта`.

### Task 11: iOS — новый груз, правка, «Отметить событие», люди, push

**Files:**
- Create: `ios/App/Account/NewShipmentView.swift`, `ios/App/Account/EditShipmentView.swift`,
  `ios/App/Account/MarkEventView.swift`, `ios/App/Account/OrgMembersView.swift`,
  `ios/App/Account/PushRegistration.swift`
- Modify: `ShipmentDetailView.swift` (кнопки «Отметить событие» при непустых `eventNodes`,
  «Изменить груз»/«Поделиться» при `canManage`), `MyShipmentsView.swift` («+» → «Новый груз» при
  `creatable orgs`), `MiddleCorridorApp.swift` (`UIApplicationDelegateAdaptor` для APNs-токена;
  нажатие на push с `ref` открывает груз), `Localizable.xcstrings`, `FakeAccountAPI.swift`
- Test: `ios/UITests/SmokeTests.swift`

**Interfaces:**
- Consumes: `AccountModel`, `AccountAPI`, `ContainerNumber`, `Labels` (Task 9–10).
- Пресеты маршрута: «Европа → Казахстан» = `ROUTE_KOSTANAY` мока, «Китай → Европа» = `ROUTE_AKTAU`
  мока (скопировать списки кодов); ручной выбор — последовательно из соседей по плечам (плечи — `MapSnapshot.segments`
  из уже загруженного снимка; морское ли плечо — по его `mode`). Форма события: только узлы из `eventNodes`; вид; причина для «стоит»;
  судно — только если следующее плечо морское. Ошибки 422 — локализованный текст по коду.
  Push: регистрация после входа, только если в сборке есть `aps-environment` (Personal Team — нет;
  тогда тихо без push и локальные уведомления остаются).
- [ ] **Step 1:** UI-тесты `test_createShipment` (неверный контейнер — кнопка неактивна, верный →
  груз в списке), `test_markEvent` (агент: «стоит» → «погодный запрет» → карточка показывает причину),
  `test_inviteAgent` (владелец: e-mail, роль агент, узел Актау → в списке людей).
- [ ] **Step 2:** FAIL → **Step 3:** реализация → **Step 4:** смоук целиком PASS.
- [ ] **Step 5:** коммит `iOS: новый груз, события, люди, push`.

### Task 12: Документация и финальная проверка

**Files:**
- Modify: `CLAUDE.md` (архитектура `services/accounts`, грабли: 404 вместо 403, Vercel без аккаунтов,
  коды стоянок, `trust_proxy`), `docs/IOS.md`, `ios/README.md` (вход, `MC_ACCOUNT_API_URL`, push
  только с платным аккаунтом), `README`/`docs` раздел «Запуск аккаунтов на Railway» (переменные,
  `python -m app.cli admin …`, проверка `MOCK_DATA=false` у сервиса — отдельный сервис, если там демо)
- [ ] **Step 1:** `pytest -q --cov`, `ruff check .`, `black --check .`, `swift test`, UI-смоук целиком.
- [ ] **Step 2:** финальное ревью ветки (opus), правки.
- [ ] **Step 3:** коммит, PR на ревью владельцу.
