# syntax=docker/dockerfile:1
# Multi-stage build for the «SpendyHolik» backend.

FROM python:3.14-slim AS builder

ENV UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies (layered for cache reuse).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and finish the virtualenv.
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/src \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

# Collect admin/Swagger static files for WhiteNoise (no DB or real secrets needed).
RUN SECRET_KEY=collectstatic-only ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

RUN useradd --create-home appuser \
    && mkdir -p /app/media \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--timeout", "60", "--access-logfile", "-"]
