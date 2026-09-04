# mc-status — Middle Corridor Status

Информационно-аналитический слой поверх Среднего коридора (TITR):
Telegram-бот + публичный канал + веб-карта (фаза 2, прототип на моках).
Ядро ценности — погодный предиктор остановки портов Каспия; плюс ручные
сводки от доверенных источников, новости, AIS.

## Команды разработки

```powershell
.venv\Scripts\activate                 # виртуальное окружение (Python 3.11)
docker compose up -d db                # Postgres на ПОРТУ 5433 (5432 занят системным!)
.venv\Scripts\python -m pytest -q      # тесты (in-memory SQLite, без сети)
.venv\Scripts\ruff check --fix .; .venv\Scripts\black .   # линт+формат (обязательно перед коммитом)
.venv\Scripts\alembic upgrade head     # миграции
.venv\Scripts\alembic revision --autogenerate -m "..."    # новая миграция
.venv\Scripts\python -m app.main      # запуск всего (API :8000 + бот + AIS)
.venv\Scripts\python -m app.scheduler.jobs weather|news   # ручной прогон джобы из терминала
$env:MOCK_DATA='true'; .venv\Scripts\python -m app.main   # API карты на синтетике, без Postgres
cd web; npm install; npm run dev                            # фронт с hot reload на :5173 (прокси /api → :8000)
cd web; npm run build                                       # web/dist → раздаёт FastAPI по /
```

Конфиг — только через ENV/`.env` (pydantic-settings, `app/config.py`).
`.env` существует локально с боевыми ключами — НЕ коммитить, НЕ печатать.

## Архитектура и границы слоёв

```
integrations/  внешние API за Protocol-интерфейсами (weather, ais, news)
services/      бизнес-логика; НЕ импортирует aiogram/fastapi
bot/           только aiogram-хендлеры/клавиатуры/тексты; вызывают services
api/           только FastAPI-роуты; вызывают services
db/            модели SQLAlchemy 2 async + repositories (запросы только тут)
scheduler/     джобы; APScheduler опционален (SCHEDULER_ENABLED, по умолчанию false)
integrations/mock/  синтетические источники для карты (MOCK_DATA=true); реализуют те же Protocol'ы
web/           фронт карты: React + Vite + TS + MapLibre; ходит только в /api/v1, типы в src/api.ts
```

- Сервисы публикуют в канал через Protocol `MessageSink` (`services/sinks.py`);
  реализация — `bot/publisher.ChannelPublisher`. Не импортировать bot из services.
- Зависимости в хендлеры бота передаются через workflow data Dispatcher’а
  (`dp["reports_service"] = ...`, параметр с тем же именем в хендлере).
- Все тексты бота — в `app/bot/texts.py` (задел под i18n). В HTML-режиме
  экранировать `<`/`>`/`&` (см. форматтеры и баг с сырым `<id>`).
- Enum'ы в БД — VARCHAR (`native_enum=False`): простые миграции + тесты на SQLite.
- Юнит-тесты бизнес-логики — на in-memory SQLite (fixtures в `tests/conftest.py`),
  внешние API — только моки (`httpx.MockTransport`, фейк-провайдеры).
- Карта: `services/map_snapshot.py` собирает `MapSnapshot` из Protocol-источников
  (узлы, суда, отправки, ветер, новости, сводки); `services/tracking.py` —
  проекция положения груза (последнее подтверждённое событие + оценка по
  расписанию, `confirmed`/`source` в ответе); `services/corridor.py` —
  статическая геометрия узлов и сегментов. Композиция источников — в
  `main.build_map_service` (мок или агрегатор+БД).

## Грабли, на которые уже наступали

- **Порт Postgres 5433**, не 5432 — на машине живёт системный Windows-Postgres,
  который перехватывает коннекты.
- structlog: нельзя передавать kwarg `event=` в logger.info (конфликт с
  позиционным именем события) — используй `event_type=` и т.п.
- Windows-консоль cp1250 не печатает эмодзи: ставь `$env:PYTHONIOENCODING='utf-8'`.
- aiogram HTML parse mode: сырой `<id>` в тексте валит сообщение
  («can't parse entities») — только `&lt;id&gt;`.
- Пороги ветра в конфиге — СТАРТОВЫЕ; калибруются по фактическим остановкам
  портов. Не «улучшать» на глаз.
- Покрытие AIS на Каспии слабое (проверено вживую: bbox Каспия почти пуст).
  Отсутствие позиции = «нет данных», не «судно стоит». MMSI паромов ASCO в
  сидax NULL — заполнять руками, когда суда появятся в эфире.
- Один инстанс бота: два polling-процесса конфликтуют по getUpdates.
- Положение груза без живой позиции — ПРОЕКЦИЯ, не факт: не рисовать её как
  подтверждённую (`position.confirmed=false`, пунктир на карте).
- Фронт: подписи узлов/грузов — HTML-маркеры (без glyph-сервера), иконки
  symbol-слоёв рисуются на canvas; тайлы CARTO без ключа. Из песочницы CI
  тайлы недоступны — карта пустая, оверлеи проверяются скриншотами.

## Продукт (для контекста решений)

- Публикации в канал: эскалация алерта до warning/critical и «отбой»; watch и
  понижение critical→warning — тихие (антиспам через жизненный цикл алерта).
- Модерация ручных сводок: AUTO_PUBLISH_REPORTS=false → /approve админом.
- Фаза 2: веб-карта — прототип на `MOCK_DATA=true` (`integrations/mock/`);
  боевой режим отдаёт порты/суда/новости из БД, отправки и поле ветра — пока
  без источника. Telegram Mini App — поверх того же `/api/v1`.
