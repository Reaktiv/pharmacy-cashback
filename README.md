# Pharmacy Cashback SaaS Platform

Multi-tenant loyalty platform for pharmacy chains in Uzbekistan. See
[`CLAUDE.md`](./CLAUDE.md) for the full domain model and architectural
decisions, and [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) for the
build order. Both are the source of truth for this project.

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (only needed if you also want to run things outside Docker)
- Node.js 22+ (only needed if you want to run the frontend outside Docker)

## Setup

Create a `.env` file at the repo root (never commit it — see
`.gitignore`) with at least:

```bash
DJANGO_SETTINGS_MODULE=config.settings
SECRET_KEY=              # generate below
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,web

FERNET_KEY=               # generate below

DATABASE_URL=postgres://pharmacy:pharmacy@localhost:5433/pharmacy_cashback
POSTGRES_DB=pharmacy_cashback
POSTGRES_USER=pharmacy
POSTGRES_PASSWORD=pharmacy

REDIS_URL=redis://localhost:6380/0

# Public HTTPS base URL Telegram sends webhooks to (CLAUDE.md §7a) — a
# tunnel URL (e.g. ngrok) for local dev, your real domain in production.
PUBLIC_BASE_URL=https://example.com
```

Generate `SECRET_KEY` and `FERNET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

See [Environment variables](#environment-variables) below for the full list,
including the extra ones needed once you put this behind a tunnel or in
production (`CSRF_TRUSTED_ORIGINS`).

## Running with Docker Compose (primary workflow)

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

This brings up the whole stack with one command: Postgres, Redis, the
Django API/web server, a Celery worker, Celery beat (scheduled jobs — see
`CELERY_BEAT_SCHEDULE` in `config/settings.py`), and the React admin panel.

- Backend API: http://localhost:8001 (host port 8001 → container port 8000)
- Health check: http://localhost:8001/healthz/
- Admin panel (React): http://localhost:5174 (host port 5174 → container 5173)
- Django admin (low-level superadmin access): http://localhost:8001/admin/
- Postgres: exposed on host port 5433 (→ container 5432)
- Redis: exposed on host port 6380 (→ container 6379)

> Host ports are intentionally non-default (5433, 6380, 8001, 5174) to avoid
> clashing with other services that might already be running on your
> machine. Containers still talk to each other on the standard ports/service
> names (`db:5432`, `redis:6379`, `web:8000`) over the compose network —
> only the host-facing mapping is shifted. Adjust the `ports:` sections in
> `docker-compose.yml` if you'd rather use the defaults and nothing else is
> bound to them.

Run tests inside Docker:

```bash
docker compose exec web pytest
```

### Seed demo data

For a realistic dataset to click through immediately (a tenant with a bot,
branches, a tenant admin, a branch manager, a seller, customers, and a
handful of transactions including a reversal):

```bash
docker compose exec web python manage.py seed_demo_data
# or, to wipe and recreate it:
docker compose exec web python manage.py seed_demo_data --reset
```

Prints the demo login credentials when done (all use the same password,
shown in the command's output). The seeded bot has a fake token, so it
won't receive real Telegram traffic — see "Adding a tenant + bot" below for
a real one.

## Running locally against a `.venv` (alternative workflow)

A virtualenv already exists at `.venv/`. To use it directly against the
Dockerized Postgres/Redis (bring up just `db` and `redis`, run Django on the
host):

```bash
docker compose up -d db redis
.venv/bin/pip install -r requirements.txt
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py runserver
```

Run the test suite from the repo root (pytest config lives in
`pyproject.toml` and points at `backend/`):

```bash
.venv/bin/pytest
```

Lint and type-check:

```bash
.venv/bin/ruff check .
.venv/bin/mypy backend/apps
```

### Frontend outside Docker

```bash
cd frontend
npm install
npm run dev
```

Defaults to proxying `/api` to `http://localhost:8001` (matching the
Docker-exposed backend port) — see `VITE_API_PROXY_TARGET` in
`vite.config.ts` if you're running the backend somewhere else.

## Production deployment

`docker-compose.yml` is dev-only (Django's `runserver`, Vite's dev server —
neither is meant to face the internet). For a real server behind a domain
with HTTPS, use `docker-compose.prod.yml` (gunicorn+uvicorn, a built
frontend served by nginx, Let's Encrypt via certbot). See
[`DEPLOY.md`](./DEPLOY.md) for the full step-by-step.

## Adding a tenant + bot

1. **Create the tenant.** Either via the React admin panel (log in as a
   superadmin → Dashboard → create tenant) or Django admin
   (`/admin/tenants/tenant/add/`). Set its `cashback_rate` (must be ≤
   `GlobalSettings.max_cashback_rate`, editable at `/admin/tenants/globalsettings/`
   or `PATCH /api/global-settings/`).
2. **Create its bot.** In Django admin (`/admin/tenants/bot/add/`) or via
   `POST /api/bots/`, pick the tenant, give it a `username` (e.g.
   `@my_pharmacy_bot`), and paste the **real** token from
   [@BotFather](https://t.me/BotFather) into the `token` field. It's
   encrypted at rest immediately (`Bot.set_token()`) — the plaintext is
   never stored or logged, and the admin form never displays it back.
3. **Webhook registration is automatic.** Saving the `Bot` row fires a
   `post_save` signal → a Celery task calls Telegram's `setWebhook` API with
   `{PUBLIC_BASE_URL}/webhook/{webhook_secret}/` — no redeploy needed. Check
   the `worker` container's logs to confirm it succeeded:
   ```bash
   docker compose logs worker --tail 20
   ```
   If it fails, the most common cause is `PUBLIC_BASE_URL` not being a real
   public HTTPS URL — Telegram requires HTTPS, so for local dev you need a
   tunnel (e.g. [ngrok](https://ngrok.com/)) pointed at your `web` service,
   with its `https://...` URL set as `PUBLIC_BASE_URL` in `.env` *before*
   creating the bot. To (re-)register webhooks for every active bot after
   changing `PUBLIC_BASE_URL`:
   ```bash
   docker compose exec web python manage.py set_webhooks
   ```
4. **Create a branch and a seller.** As that tenant's admin (React panel →
   Tenant → add a branch; Sellers page → add a seller, which also creates
   their login). The seller logs into the fast register page at
   `/seller/` (session-based login at `/accounts/login/`) — not the JWT API
   the React panel and Telegram bot use.
5. **Customers register themselves** by messaging the bot and tapping
   "Share my phone number" — no admin action needed.

## Project layout

```
pharmacy-cashback/
  backend/
    config/                 # settings, urls, celery, wsgi/asgi
    apps/
      tenants/               # Tenant, GlobalSettings, Bot, tenant middleware, TenantManager
      accounts/               # roles, Branch, Seller, JWT auth, seed_demo_data command
      customers/              # Customer, PendingCashback, OTP
      ledger/                 # Transaction, services.py (ALL cashback math), reports.py
      bot/                    # Aiogram multibot, handlers, webhook view, notification tasks
      broadcasts/              # Broadcast model, throttled Celery sending
      audit/                   # AuditLog (append-only)
      seller_web/               # the fast seller register page
    tests/
  frontend/                 # React admin panel (Vite + TS)
  docker-compose.yml        # dev stack (runserver, vite dev server)
  docker-compose.prod.yml   # production stack (gunicorn+uvicorn, built
                             # frontend behind nginx+TLS) — see DEPLOY.md
  README.md
```

## Environment variables

All read via `django-environ` from a `.env` file at the repo root (never
commit it — see `.gitignore`). See [Setup](#setup) above for the required
set and how to generate secrets.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django's cryptographic signing key. |
| `DEBUG` | `True` for local dev, `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated `https://...` origins, needed once you're behind a tunnel (ngrok/jprq) or a real domain — otherwise browser POSTs (login, seller-web) get a 403. |
| `FERNET_KEY` | Encrypts `Bot.token_encrypted` (CLAUDE.md §5). |
| `DATABASE_URL` | Postgres connection string. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Used by the `db` container and folded into `DATABASE_URL` for the app containers. |
| `REDIS_URL` | Celery broker/result backend. |
| `PUBLIC_BASE_URL` | Public HTTPS base URL Telegram sends webhooks to (CLAUDE.md §7a). |

Production-only (see `DEPLOY.md`): `DOMAIN`, `CERTBOT_EMAIL`.
