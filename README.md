# mc-status — Middle Corridor Status

Информационно-аналитический слой поверх Среднего коридора (TITR):
Telegram-бот + публичный канал с погодными алертами по портам, позициями судов,
новостями и оперативными данными от доверенных источников.

> README пополняется по мере реализации. Полная инструкция по деплою — на шаге 9.

## Локальный запуск (черновик)

```bash
# 1. Poднять Postgres
docker compose up -d db

# 2. Виртуальное окружение и зависимости
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

# 3. Конфигурация
copy .env.example .env           # и заполнить BOT_TOKEN и прочее

# 4. Запуск
python -m app.main
```

- `GET http://localhost:8000/health` — проверка живости (`db: true`, если Postgres доступен).
- Без `BOT_TOKEN` приложение поднимает только HTTP-часть.

## Тесты и линт

```bash
pytest
ruff check .
black --check .
```
