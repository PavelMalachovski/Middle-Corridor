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
cd web; npm run lint; npm test; npm run typecheck           # Biome + Vitest + tsc (обязательно перед коммитом)
cd web; npm run e2e                                         # Playwright: нужен build; API с MOCK_DATA поднимет сам (или возьмёт :8000)
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
web/           фронт карты: React 19 + Vite 8 + TS 7 + MapLibre 6; ходит только в /api/v1, типы в src/api.ts
               src/live.ts — SSE/поллинг/replay; src/replay.ts + replayClock.ts — шкала времени;
               src/map/animate.ts — интерполятор движения; components/sheet.ts — геометрия шторки;
               src/map/windParticles.ts — WebGL-слой частиц ветра (windGrid.ts — текстура поля);
               src/forecast.ts + components/charts/ — прогноз и SVG-графики; src/urlState.ts — состояние в адресе;
               src/i18n/ — словари ru/en (ru.ts — источник ключей), t()/useI18n(), labels.ts — подписи из кодов бэкенда;
               *.test.ts рядом с кодом (Vitest), e2e/ — Playwright, biome.json — линт и формат
api/index.py   точка входа Vercel (serverless FastAPI: только /api/v1 и /health); vercel.json — маршрутизация
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
- Vercel — только статика + функции: бот/AIS/планировщик там не живут, это
  Railway. `requirements.txt` — зеркало pyproject (тест следит); фронт на
  другом домене ходит в API через `VITE_API_BASE` + `CORS_ORIGINS`.
- Положение груза без живой позиции — ПРОЕКЦИЯ, не факт: не рисовать её как
  подтверждённую (`position.confirmed=false`, пунктир на карте).
- MapLibre 6: только WebGL 2 (без него — `MapFallback`), импорт `import * as
  maplibregl`. Dev-пребандл Rolldown дублирует maplibre-gl-shared и валидатор
  стиля не знает `line-layer-opacity` — поэтому `optimizeDeps.exclude:
  ["maplibre-gl"]`; в production-сборке дубля нет.
- CSS MapLibre приезжает с ленивым чанком карты, то есть ПОСЛЕ styles.css:
  переопределения `.maplibregl-*` и контейнер карты держим на специфичности
  `.app .map` / `.map .maplibregl-…`, иначе `.maplibregl-map { position:
  relative }` схлопывает карту в 0 px.
- Слежение камерой: покадровый `jumpTo` вызывает `map.stop()`, который
  сбрасывает обработчики жестов. Слежение снимаем СИНХРОННО в обработчике
  `dragstart`/`wheel`/`zoomstart` (`followState.current`), не через React-
  состояние — иначе drag превращается в click и снимает выбор груза.
- Replay: «сейчас» — по серверным часам (`server_time` снимка + прошедшее у
  клиента), не по `Date.now()`: с `MOCK_TIME_SCALE` они расходятся в сотни
  раз. Окно ±N ч задаёт бэкенд (`snapshot.live`), у краёв держим отступ 15
  мин — иначе сервер отвечает 400.
- Ветер в replay — троттлинг (раз в 1,5 с), не дебаунс: при воспроизведении
  `replayAt` меняется каждые 400 мс, и дебаунс не сработал бы никогда.
- Vitest: логику держать в чистых модулях (`replayClock.ts`, `sheet.ts`,
  `geo.ts`, `animate.ts`), React-компоненты тестировать через jsdom
  (`// @vitest-environment jsdom`, см. ErrorBoundary.test.tsx).
- Playwright в песочнике: браузер Chromium из `/opt/pw-browsers/chromium`
  через `PLAYWRIGHT_CHROMIUM_PATH`, тайлы недоступны — карта чёрная,
  проверяем оверлеи; `page.goto` с `networkidle` зависает из-за SSE — только
  `domcontentloaded`. Песочница — Chromium 141, CI — 151 (Playwright 1.62).
- E2E импортируют `test` из `e2e/fixtures.ts`, не из `@playwright/test`: на
  падении в stdout (лог джобы CI) печатаются ошибки консоли/страницы,
  состояние карты и след камеры (`[map.easeTo]`, `[map.setTerrain]`,
  `[map.dom.change]`). Артефакты CI из песочницы не скачать (прокси).
- 3D-рельеф под SwiftShader: первый кадр с terrain — 3–4 с компиляции
  шейдеров на главном потоке плюс 5–9 с растеризации; второй кадр анимации
  камеры приходит через 10+ с (в CI — позже таймаута), pitch «висит» на 0.
  Исключений нет, промис кадра MapLibre глотает ошибки молча — искать через
  след камеры, не через консоль. E2E 3D закрепляет
  `contextOptions.reducedMotion: "reduce"` (MapLibre делает easeTo → jumpTo),
  стрелки вместо частиц и `test.slow()`; проверяем проводку, не рендер.
- В командах для песочницы использовать абсолютные пути: рабочий каталог
  прыгает между корнем и `web/`, `npm install` не в том каталоге создаёт
  мусорный package.json в корне.
- MapLibre 6 в проде: воркер грузится отдельным файлом — без
  `import url from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"` +
  `setWorkerUrl(url)` на Vercel 404 и чёрная карта (dev-сервер маскирует).
- Мобильная шторка: высота от `window.innerHeight` (хук `useViewportHeight`),
  не `vh` — на телефоне `100vh` больше видимой области, шторка накрывает шкалу.
  Скорость флика — по `e.timeStamp` событий, не по `performance.now()` в
  обработчике: пока главный поток рисует кадр карты, обработчик опаздывает,
  и настоящий флик выглядел как медленное перетаскивание (флак e2e и на
  слабом телефоне).
- Частицы ветра: проекция только через `projectTile` из прелюдии MapLibre
  (свои матрицы расходятся с глобусом/наклоном); экранный буфер следа
  сбрасывать при смене матрицы, иначе след «плывёт» за камерой. SwiftShader в
  CI частицы не тянет — мобильный e2e закрепляет `windMode: "arrows"`.
- Biome: `gl.useProgram` принимает за React-хук (`useHookAtTopLevel`) —
  обёртка `activateProgram` с `biome-ignore`; `role="group"` на div/span
  бракует `useSemanticElements` — использовать `<fieldset>` + `<legend
  class="sr-only">` (стили fieldset сброшены в CSS).
- i18n: все строки интерфейса — через ключи (`t()` вне React, `useI18n()` в
  компонентах; язык меняется — эффекты маркеров получают `lang` в deps).
  Бэкенд обязан отдавать КОДЫ (событие/причина стоянки/фаза/порт) рядом с
  русской строкой — по-английски фронт собирает подпись из кода; новая
  русская строка без кода останется русской в EN. Playwright закреплён на
  `locale: "ru-RU"`, иначе браузер с английской локалью ломает русские тексты.
- Deep link `?at=`: применять только после первого снимка (нужны серверные
  часы и окно replay), «сейчас» экстраполировать с `live.time_scale` — иначе
  через минуту 400 от сервера при `MOCK_TIME_SCALE`.
- Фронт: подписи узлов/грузов — HTML-маркеры (без glyph-сервера), иконки
  symbol-слоёв рисуются на canvas. Подложки — пресеты в `web/src/map/style.ts`
  с цепочкой кандидатов (вектор без ключа → растр CARTO/Esri); стиль
  проверяется fetch'ем до `setStyle`, наши слои пересоздаются на каждый
  `style.load`. Не перезаписывать `className` у элементов маркеров
  (слетает `maplibregl-marker`) — только `setOwnClasses`. Из песочницы CI
  тайлы недоступны — карта пустая, оверлеи проверяются скриншотами.

## Продукт (для контекста решений)

- Публикации в канал: эскалация алерта до warning/critical и «отбой»; watch и
  понижение critical→warning — тихие (антиспам через жизненный цикл алерта).
- Модерация ручных сводок: AUTO_PUBLISH_REPORTS=false → /approve админом.
- Фаза 2: веб-карта — прототип на `MOCK_DATA=true` (`integrations/mock/`);
  боевой режим отдаёт порты/суда/новости из БД, отправки и поле ветра — пока
  без источника. Сделано: живая карта с частицами ветра, replay, графики и
  прогноз, поиск/фильтры/ссылки (`?s=&view=&basemap=&at=`), RU/EN.
  Следующее — Telegram Mini App поверх того же `/api/v1`.
