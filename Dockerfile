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

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install .

# Собранный фронт раздаёт FastAPI (WEB_DIST_DIR, по умолчанию web/dist)
COPY --from=web /web/dist ./web/dist

EXPOSE 8000

# Миграции применяются на старте, затем поднимается процесс (API + бот + AIS)
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
