# SpendyHolik — Backend

REST API и фоновые задачи для SpendyHolik — приложения учёта личных финансов:
счета, операции, категории, бюджеты, цели, регулярные платежи, долги и аналитика.

## Стек

- Python 3.14, Django 6.0, Django REST Framework, pydantic v2
- PostgreSQL 18, Redis 8, Celery + django-celery-beat
- JWT (simplejwt, ротация refresh-токенов), OpenAPI 3 (drf-spectacular)
- pytest, ruff, uv

## Архитектура

Чистая архитектура: каждый модуль (`accounts`, `finances`, `goals`,
`recurring`, `debts`, `analytics`, `notifications`) разбит на слои,
зависимости направлены внутрь.

```
src/<модуль>/
├── domain/          сущности, value objects, доменные исключения (чистый Python)
├── application/     use cases, порты (интерфейсы репозиториев), DTO
├── infrastructure/  Django ORM, репозитории, внешние сервисы
└── interfaces/      DRF views и маршруты
```

- `shared/` — общий код: `Money`, часы, UnitOfWork, PATCH-хелпер.
- `domain` и `application` не импортируют Django/DRF.
- Суммы в API — в минорных единицах: `{"minor": 124000, "currency": "RUB", "formatted": "1 240 ₽"}`.
- Аналитика пересчитывает суммы в базовую валюту пользователя по курсам.

## Быстрый старт

Нужны [uv](https://docs.astral.sh/uv/) и Docker.

```bash
docker compose up -d              # PostgreSQL и Redis
cp .env.example .env
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Swagger UI — http://localhost:8000/api/docs/, схема OpenAPI — `/api/schema/`,
проверки — `/health/` и `/ready/`.

## Тесты и линтеры

```bash
uv run pytest                     # unit + API (локально на SQLite)
uv run ruff check . && uv run ruff format --check .
```

Тесты на PostgreSQL (как в CI):

```bash
TEST_DATABASE_URL=postgres://spendyholik:spendyholik@localhost:5432/spendyholik uv run pytest
```

- `tests/unit/` — домен и use cases на in-memory фейках, без БД.
- `tests/api/` — контракт API, права доступа, число SQL-запросов.

## Деплой

Kubernetes (k3s) + Helm-чарт `deploy/charts/spendyholik-backend` (api, worker,
beat, PostgreSQL, Redis, миграции, Traefik ingress, TLS через cert-manager).
После зелёного CI в `main` GitHub Actions собирает образ в GHCR и обновляет
сервер по SSH. Пошаговая инструкция — [DEPLOY.md](DEPLOY.md).
