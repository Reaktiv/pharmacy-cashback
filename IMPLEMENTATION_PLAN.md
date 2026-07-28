# IMPLEMENTATION_PLAN.md — build in this exact order

Read `CLAUDE.md` first. Build one phase at a time. After each phase: run tests,
run migrations, boot the app, summarize, then stop for review before the next
phase.

---

## Phase 0 — Foundation & scaffolding
**Goal:** an empty but runnable, dockerized Django project.
- Create the repo layout from CLAUDE.md §9.
- Django 5 project `config`, PostgreSQL settings via django-environ.
- Docker Compose: `db` (postgres), `redis`, `web` (django), `worker` (celery).
- `.env.example` with every variable (DB, REDIS_URL, FERNET_KEY, SECRET_KEY,
  DJANGO_SETTINGS_MODULE, etc.).
- pytest + pytest-django + ruff configured. One trivial passing test.
- README with "how to run locally" (docker compose up).
**Done when:** `docker compose up` boots web+worker+db+redis and `pytest` is green.

## Phase 1 — Tenancy core (the security backbone)
**Goal:** enforced multi-tenant isolation before any business data exists.
- `apps/tenants`: `Tenant`, `GlobalSettings` (singleton), `Bot` (token
  encrypted via Fernet).
- `TenantScopedModel` abstract base + `TenantManager` (default queryset requires
  tenant; explicit `all_tenants()` escape hatch).
- Middleware resolving current tenant into a `ContextVar` (from user for web;
  stub for bot until Phase 5).
- Enforce `Tenant.cashback_rate <= GlobalSettings.max_cashback_rate` in
  `clean()`.
- **Write the mandatory isolation test now** (§4) using two dummy tenant-scoped
  models — it must fail-closed.
**Done when:** isolation test passes; a query without tenant context raises or
returns empty, never leaks.

## Phase 2 — Accounts, roles, auth
**Goal:** internal users with roles.
- Extend user model / add profile with role (superadmin, tenant_admin,
  branch_manager, seller).
- `Branch`, `Seller` models.
- DRF + JWT auth. Role-based permission classes:
  `IsSuperadmin`, `IsTenantAdmin`, `IsBranchManager`, `IsSeller`.
- Tenant resolution from the authenticated user in middleware.
**Done when:** a seller token is scoped to one branch/tenant; a tenant admin
cannot hit superadmin endpoints (tested).

## Phase 3 — Customers & the ledger (the heart)
**Goal:** the transaction ledger and all cashback math.
- `Customer`, `PendingCashback`, `OTP` models (customers app).
- `Transaction` model exactly per CLAUDE.md §5, with DB check constraints
  (non-negative amounts).
- `apps/ledger/services.py`: `round_down_1000`, `calculate_earn`,
  `calculate_redemption`, `post_earn_transaction` (atomic +
  `select_for_update`), `post_reversal`, `get_balance`.
- Unit tests for EVERY §2 rule: earn-on-cash-only, 50% cap, min-redeem,
  round-down-1000, rate snapshot, no-cashback checkbox, reversal, idempotency,
  balance = ledger sum, no infinite loop.
**Done when:** all domain-rule tests pass; balance is always ledger-derived.

## Phase 4 — Seller web page (fast register UI)
**Goal:** end-to-end earn + redeem from the till.
- Server-rendered fast page in `apps/seller_web` (two inputs + checkbox; Enter
  submits). Auth = seller login, auto-scoped.
- Earn flow: amount + phone (+ optional no_cashback) → service → confirmation.
- If phone has no Customer yet → create PendingCashback and still show success.
- Redeem flow: seller enters the customer's OTP → validate (unexpired, unused,
  right tenant) → post spend → confirmation.
- Idempotency key generated per submit to block double-post.
**Done when:** a seller earns and redeems for a real customer, balances update
correctly, disputes impossible via double-submit.

## Phase 5 — Telegram bot (multibot)
**Goal:** customer-facing bot for all tenants from one process.
- Aiogram 3 multibot; webhook view `POST /webhook/<webhook_secret>` resolving
  tenant from the secret.
- `/start` → branded welcome → **request_contact only** → consent → register →
  claim matching unexpired PendingCashback → show balance.
- Balance view; Redeem flow (ask amount → issue OTP → display code).
- Celery notification task fired by `post_earn_transaction` / spend / reversal:
  "points added/spent, balance, [Report]".
- Bot token stored encrypted; adding a Bot row auto-registers its webhook (no
  redeploy). Provide a management command / signal to set webhooks.
**Done when:** registering a bot token in admin makes that bot live; a purchase
notifies the customer; customer registers and claims pending points.

## Phase 6 — Fraud mitigation (cheap layers)
**Goal:** make fraud visible and unprofitable.
- Enforce hard limits: max check amount, per-seller daily txn limit,
  per-customer daily redemption count.
- [Report] button → creates a manager-visible flag.
- Daily per-seller summary task to the branch manager.
- Add `flagged` + `suspicion_score` stub fields (populated later).
**Done when:** limits are enforced with clear errors; reports reach managers.

## Phase 7 — Admin API + React frontend
**Goal:** the centralized panel.
- DRF endpoints: tenants CRUD (superadmin), bots/tokens, branches, sellers,
  rate setting (cap-enforced), reversals (manager), reports, broadcasts.
- Reports endpoints: cross-tenant summary (superadmin dashboard incl. total
  liability), per-branch, per-seller, daily earn/spend.
- React (Vite + TS) in `/frontend`: login, superadmin dashboard table
  (Bot | Tenant | Customers | Active(30d) | Today | Total liability | Status),
  tenant drill-down, rate settings, broadcast composer, reports views.
- Keep Django admin enabled for low-level superadmin access.
**Done when:** superadmin sees the cross-tenant table; tenant admin sets rate
(rejected above cap) and sends a broadcast; reports render.

## Phase 8 — Broadcasts & polish
**Goal:** promotions at scale + hardening.
- Broadcast model + Celery sending with throttling (~25 msg/sec), skip blocked
  users, record sent/failed counts.
- AuditLog wired to: rate changes, reversals, tenant/token changes, broadcasts.
- Final pass: seed/demo data command, full README (setup, env, add-a-tenant
  guide), run the whole DoD checklist in CLAUDE.md §10.
**Done when:** the §10 Definition of Done checklist is fully green.

---

### After every phase, report back in this format:
- What was built (files added/changed).
- Tests added and their result.
- Any deviation from CLAUDE.md and why (should be none).
- What's next.
