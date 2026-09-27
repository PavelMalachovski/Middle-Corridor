# --- Фронт: web/ → web/dist (React + Vite) -----------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

# --- Бэкенд: API + бот + AIS в одном процессе ---------------------------------
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Процесс работает без root; писать в /app ему не нужно (миграции — только в БД)
RUN useradd --no-log-init -r -u 10001 app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Байткод собираем на сборке: от имени app каталог /app только на чтение
RUN pip install . && python -m compileall -q app alembic

# Собранный фронт раздаёт FastAPI (WEB_DIST_DIR, по умолчанию web/dist)
COPY --from=web /web/dist ./web/dist

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health', timeout=4)"

# Миграции применяются на старте, затем поднимается процесс (API + бот + AIS)
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
