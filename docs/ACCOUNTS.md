# Аккаунты: запуск на Railway

Аккаунты (вход по коду, грузы компаний, события, push) живут только там, где есть `AUTH_SECRET`,
`MOCK_DATA=false` и не Vercel (`Settings.accounts_enabled`). Публичное демо (Vercel, `MOCK_DATA=true`)
аккаунтов не поднимает.

## Сервис

Если текущий сервис Railway отдаёт демо (`MOCK_DATA=true`) — завести **отдельный** сервис с
`MOCK_DATA=false` и своей базой Postgres. Не переключать демо: оно нужно для показа и iOS-смоука.

## Переменные

| Переменная | Значение |
|---|---|
| `DATABASE_URL` | Postgres сервиса (`postgresql+asyncpg://…`) |
| `MOCK_DATA` | `false` |
| `AUTH_SECRET` | длинная случайная строка; пусто = аккаунты выключены |
| `EMAIL_PROVIDER` | `resend` (по умолчанию `log` — коды только в лог) |
| `EMAIL_API_KEY`, `EMAIL_FROM` | ключ Resend и подтверждённый адрес отправителя |
| `TRUST_PROXY` | `true` (Railway стоит за прокси; иначе лимит по IP общий на всех) |
| `TRUSTED_PROXY_HOPS` | `1` — сколько прокси дописывают `X-Forwarded-For` |
| `CORS_ORIGINS` | origin'ы фронта через запятую, если он на другом домене |
| `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_P8`, `APNS_BUNDLE_ID`, `APNS_ENV` | push, см. ниже; пусто = выключен |

## Миграции

```bash
alembic upgrade head
```

CI гоняет миграции туда-обратно и `alembic check`.

## Первый запуск (bootstrap)

Команды — `python -m app.cli`, на Railway через `railway run` или shell сервиса. Почты — свои:

```bash
python -m app.cli admin --email owner@example.com                       # админ платформы
python -m app.cli org create --kind forwarder --name "Forwarder LLC"    # печатает id компании
python -m app.cli org create --kind client --name "Client LLC"
python -m app.cli org link --forwarder 1 --client 2                     # экспедитор видит грузы клиента
python -m app.cli invite --org 1 --email agent@example.com --role agent [--nodes aktau,baku]
python -m app.cli user disable --email gone@example.com                 # отключить пользователя
```

`--kind`: forwarder | client | platform; `--role`: owner | admin | agent | viewer.

Как войти первым: `admin --email owner@example.com` → в приложении ввести эту почту → код придёт
письмом (при `EMAIL_PROVIDER=log` — в логе сервиса) → дальше приглашать людей через `invite` или
экран «Люди» в приложении.

## Push (iOS)

1. Платный аккаунт Apple Developer (бесплатный Apple ID не даёт `aps-environment`).
2. Ключ APNs (.p8) в Certificates, Identifiers & Profiles → Keys; записать Key ID и Team ID.
3. На сервисе: `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_P8` (PEM целиком), `APNS_ENV=sandbox|production`.
4. В `ios/project.yml`: `MC_PUSH_ENABLED: "YES"` и entitlement `aps-environment` у цели App;
   `MC_ACCOUNT_API_URL` — адрес сервиса.
5. Без этого приложение шлёт локальные уведомления по грузам аккаунта (раз в минуту на переднем плане).
