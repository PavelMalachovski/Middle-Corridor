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

EXPOSE 8000

# Миграции применяются на старте, затем поднимается процесс (API + бот + AIS)
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
