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
.venv/bin/pip install -r backend/requirements.txt
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
  docker-compose.yml
  .env.example
  README.md
```

## Environment variables

See `.env.example` for the full list with descriptions (`SECRET_KEY`,
`FERNET_KEY`, `DATABASE_URL`, `REDIS_URL`, `PUBLIC_BASE_URL`, `ALLOWED_HOSTS`,
etc.). Never commit a real `.env`.
