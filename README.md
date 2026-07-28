# Pharmacy Cashback SaaS Platform

Multi-tenant loyalty platform for pharmacy chains in Uzbekistan. See
[`CLAUDE.md`](./CLAUDE.md) for the full domain model and architectural
decisions, and [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) for the
build order. Both are the source of truth for this project.

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (only needed if you also want to run things outside Docker)

## Setup

```bash
cp .env.example .env
# edit .env: generate a real SECRET_KEY and FERNET_KEY, see comments in the file
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Running with Docker Compose (primary workflow)

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

- Web: http://localhost:8001 (host port 8001 → container port 8000)
- Health check: http://localhost:8001/healthz/
- Postgres: exposed on host port 5433 (→ container 5432)
- Redis: exposed on host port 6380 (→ container 6379)

> Host ports for db/redis/web are intentionally non-default (5433, 6380, 8001)
> to avoid clashing with other services that might already be running on
> your machine. Containers still talk to each other on the standard ports
> (`db:5432`, `redis:6379`) over the compose network — only the host-facing
> mapping is shifted. Adjust the `ports:` section in `docker-compose.yml` if
> you'd rather use the defaults and nothing else is bound to them.

Run tests inside Docker:

```bash
docker compose exec web pytest
```

## Running locally against a `.venv` (alternative workflow)

A virtualenv already exists at `.venv/`. To use it directly against the
Dockerized Postgres/Redis (bring up just `db` and `redis`, run Django on the
host):

```bash
docker compose up -d db redis
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py runserver
```

Run the test suite from the repo root (pytest config lives in
`pyproject.toml` and points at `backend/`):

```bash
.venv/bin/pytest
```

Lint:

```bash
.venv/bin/ruff check .
```

## Adding a tenant + bot

Not yet implemented — this lands in Phase 5 per `IMPLEMENTATION_PLAN.md`.
This section will document creating a `Tenant`, `Branch`, and `Bot` (with its
Telegram token) and how the webhook gets auto-registered.

## Project layout

```
pharmacy-cashback/
  backend/
    config/                 # settings, urls, celery, wsgi/asgi
    apps/                   # tenants, accounts, customers, ledger, bot, broadcasts, audit, seller_web
    tests/
  frontend/                 # React admin panel (Vite + TS) — added in Phase 7
  docker-compose.yml
  .env.example
  README.md
```

## Environment variables

See `.env.example` for the full list with descriptions (`SECRET_KEY`,
`FERNET_KEY`, `DATABASE_URL`, `REDIS_URL`, etc.). Never commit a real `.env`.
