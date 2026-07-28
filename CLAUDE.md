# CLAUDE.md — Pharmacy Cashback SaaS Platform

> This file is the single source of truth for this project. Read it fully before
> writing any code. Every architectural decision here is deliberate — do not
> "improve" or deviate without asking. When in doubt, follow this document literally.

---

## 1. What we are building (one paragraph)

A multi-tenant SaaS loyalty platform for pharmacy chains in Uzbekistan. Each
pharmacy chain ("tenant") gets its own branded Telegram bot where customers earn
**cashback points** on purchases and redeem them on future purchases. Sellers
(cashiers) enter transactions through a simple web page at the register. A
centralized web admin panel lets the superadmin manage all tenants and view
cross-tenant statistics, while each chain's admin manages only their own data.
The goal is not to make customers buy *more* medicine — it is to make them
**choose this pharmacy** over competitors nearby.

---

## 2. Core domain rules (MEMORIZE THESE — they drive everything)

These are business-critical invariants. Violating any of them either loses the
pharmacy money or breaks the law.

1. **Cashback is POINTS, not money.** Never call it money, never let it convert
   to cash, never let it pay 100% of a bill. Points = a discount mechanism. This
   keeps us out of payment-licensing regulation.

2. **Cashback is earned ONLY on the cash-paid portion**, never on the
   cashback-paid portion. This prevents an infinite growth loop.
   `cashback_earned = round_down(cash_paid * rate)`.

3. **Redemption is capped at 50% of the check total.** The customer must always
   pay at least 50% in cash. `max_redeemable = check_amount * 0.50`.

4. **Rate is set per-tenant but bounded by a global cap** the superadmin
   controls (e.g. tenant can choose 1–15%, cap = 15%). A tenant can never exceed
   the global cap.

5. **Rate changes affect only FUTURE transactions.** Each transaction stores the
   `cashback_rate` in effect at the time. Never retroactively recompute.

6. **Balance is NEVER stored as a mutable column.** Balance is always computed
   as the sum of a customer's transactions
   (`SUM(earned) - SUM(spent) - SUM(reversed)`). Transactions are the source of
   truth. (A cached balance for read-performance is allowed later, but the
   ledger is authoritative.)

7. **Corrections are reversals, not deletions.** To undo a transaction, insert a
   `reversal` transaction that negates it. Never DELETE or UPDATE a posted
   transaction's amounts.

8. **Minimum check amount to redeem** (configurable per tenant, e.g. 20,000 UZS).
   Below this, points can be earned but not spent — keeps the register fast.

9. **Rounding: always round DOWN to the nearest 1,000 UZS** for both earned and
   spent points. Uzbekistan has no small change; fractional points cause
   register disputes.

10. **All money values use Python `Decimal`, never `float`.** DB columns are
    `DecimalField(max_digits=12, decimal_places=2)`.

11. **Cashback prescription handling (MVP decision):** For the MVP we use ONE
    flat rate on the WHOLE check. We do NOT build a drug database. However, the
    seller page MUST include a **"No cashback (prescription only)" checkbox**
    that, when checked, records the sale with `cashback_earned = 0`. This is our
    legal safety valve. (Category-level rates are a future enhancement, not now.)

---

## 3. Roles & permissions

| Role | Scope | Can do |
|------|-------|--------|
| **Superadmin** | Global (all tenants) | Create tenants, add/rotate bot tokens, set global rate cap, view cross-tenant stats. Cannot see individual customer PII unless drilling into one tenant. |
| **Tenant Admin** | One tenant | Manage branches, set cashback rate (within cap), send broadcasts, view own reports, manage managers/sellers. |
| **Branch Manager** | One branch | View own branch stats, manage own sellers, see flagged/suspicious activity, issue reversals. |
| **Seller** | One branch | Only: create earn transactions, confirm redemptions via OTP. No reports, no reversals. |
| **Customer** | Self | Via Telegram bot only: view balance, get notifications, generate redemption OTP, see promotions. |

Sellers, managers, and admins are internal users (authenticate to the web app).
Customers are external (authenticate only implicitly via Telegram).

---

## 4. Multi-tenancy — THIS IS THE MOST SECURITY-CRITICAL PART

We use **logical isolation** (shared database, `tenant_id` on every row), NOT
physical database separation. Reason: the superadmin needs a unified
cross-tenant statistics view, which physical separation makes very hard.

Implement isolation in THREE enforced layers:

1. **`tenant_id` (FK to Tenant) on every tenant-scoped table.** No exceptions.
2. **A `TenantManager` / scoped queryset** so that the default manager cannot
   return rows without a tenant filter. Provide an explicit
   `all_tenants()` escape hatch used ONLY by superadmin code and clearly named.
3. **Request middleware** that resolves the current tenant (from the
   authenticated user for web, from the bot token for Telegram webhooks) and
   stores it in a `contextvars.ContextVar`. The tenant manager reads from this.

**MANDATORY TEST (must exist and pass on every commit):**
`test_tenant_a_admin_cannot_read_tenant_b_data` — asserts that a query as
Tenant A's admin returns zero rows belonging to Tenant B, for Customer,
Transaction, Branch, and Seller.

A single missing tenant filter is a data breach that kills the business. Treat
this like a security boundary, because it is one.

---

## 5. The data model (authoritative)

Use Django models. All tenant-scoped models inherit from an abstract
`TenantScopedModel` that adds `tenant = FK(Tenant)` and uses the tenant manager.

### Tenant
- `id`, `name`, `slug` (unique)
- `is_active` (bool)
- `cashback_rate` (Decimal, percent, e.g. 3.00) — the chain's chosen rate
- `min_redeem_amount` (Decimal, default 20000)
- `points_expiry_days` (nullable int; null = never expire) — default null
- `created_at`

### GlobalSettings (singleton, superadmin only)
- `max_cashback_rate` (Decimal, e.g. 15.00) — the hard cap for all tenants
- `max_redeem_percent` (Decimal, default 50.00)
- `max_check_amount` (Decimal — flag/block checks above this, e.g. 2000000)

Enforce `Tenant.cashback_rate <= GlobalSettings.max_cashback_rate` in
`Tenant.clean()` and in the admin serializer.

### Bot (one row per tenant's Telegram bot)
- `tenant` (FK, one-to-one for MVP)
- `token_encrypted` (encrypted at rest — use a Fernet key from env, NEVER store
  plaintext token)
- `username` (e.g. @dorimed_bot)
- `webhook_secret` (random, used in the webhook URL path instead of the token)
- `is_active`

### Branch
- `tenant` (FK), `name`, `address`, `is_active`

### Seller
- `tenant` (FK), `branch` (FK)
- `user` (FK to Django User — sellers log into the web app)
- `phone`, `full_name`, `is_active`
- Daily limits: `daily_txn_limit` (nullable int), inherited from tenant default

### Customer
- `tenant` (FK)
- `telegram_id` (nullable — null until they register in the bot)
- `phone` (E.164 normalized, e.g. +998901234567)
- `full_name`
- `consent_given_at` (nullable datetime — PII consent)
- `is_active`
- `created_at`
- UNIQUE constraint on `(tenant, phone)`.
- A `telegram_id` is unique per tenant when not null.

### Transaction (THE LEDGER — the heart of the system)
- `tenant` (FK), `branch` (FK), `customer` (FK), `seller` (FK, nullable for
  reversals issued by a manager)
- `check_amount` (Decimal) — total bill
- `cashback_earned` (Decimal, >= 0)
- `cashback_spent` (Decimal, >= 0)
- `cash_paid` (Decimal) — = check_amount - cashback_spent
- `cashback_rate` (Decimal) — rate snapshot at time of txn
- `type` (choices: `earn`, `spend`, `reversal`) — note a single register action
  can both spend and earn; model this as: `type='earn'` rows may also carry a
  positive `cashback_spent`. Keep `reversal` separate.
- `status` (choices: `active`, `reversed`)
- `reverses` (nullable FK to the Transaction this reverses)
- `no_cashback` (bool) — true when the prescription-only checkbox was ticked
- `idempotency_key` (unique per tenant — prevents double-submit)
- `created_at`

### PendingCashback (for customers not yet registered in the bot)
- `tenant` (FK), `phone`, `amount` (Decimal), `source_transaction` (FK)
- `expires_at` (datetime — default now + 30 days)
- `claimed` (bool)
When a customer registers with a matching phone, move all unexpired unclaimed
PendingCashback into their ledger as an `earn` transaction, then mark claimed.

### OTP (redemption codes)
- `tenant`, `customer`, `code` (6 digits), `amount_requested` (Decimal)
- `expires_at` (now + 5 min), `used` (bool)
Single-use, short-lived. Store hashed if you want extra safety; plaintext is
acceptable for MVP given 5-min expiry.

### Broadcast (promotions / announcements)
- `tenant`, `title`, `body`, `created_by`, `created_at`
- `status` (draft/sending/sent), `sent_count`, `failed_count`

### AuditLog (append-only)
- `tenant` (nullable for global actions), `actor` (user), `action` (string),
  `target_type`, `target_id`, `metadata` (JSON), `created_at`
Log: rate changes, reversals, manual balance actions, tenant creation, token
changes. Append-only — never edited.

---

## 6. Core business logic (put this in a service layer, not in views)

Create `apps/ledger/services.py`. Views and bot handlers call these; they never
compute cashback inline.

### `calculate_earn(check_amount, cash_paid, rate) -> Decimal`
`return round_down_1000(cash_paid * rate / 100)`

### `calculate_redemption(check_amount, requested, customer_balance, tenant) -> Decimal`
1. If `check_amount < tenant.min_redeem_amount`: return 0 (cannot redeem).
2. `cap = check_amount * (max_redeem_percent / 100)`.
3. `allowed = min(requested, cap, customer_balance)`.
4. `return round_down_1000(allowed)`.

### `post_earn_transaction(tenant, branch, seller, customer, check_amount, cashback_spent=0, no_cashback=False, idempotency_key) -> Transaction`
- Validate idempotency_key not already used → if used, return existing txn.
- `cash_paid = check_amount - cashback_spent`.
- `earned = 0 if no_cashback else calculate_earn(check_amount, cash_paid, tenant.cashback_rate)`.
- Wrap in `transaction.atomic()` + `select_for_update()` on the customer to
  prevent race conditions.
- Re-check balance covers `cashback_spent` inside the lock.
- Create Transaction, send bot notification (via Celery task), return it.

### `post_reversal(original_txn, actor) -> Transaction`
- Create a `reversal` transaction negating the original's earned/spent.
- Set original's `status = 'reversed'`.
- Write AuditLog. Balance may go negative temporarily — that's allowed; it
  self-heals from future earns.

### `get_balance(customer) -> Decimal`
`SUM(earned) - SUM(spent)` over `active` transactions, plus reversal effects.
Compute in one aggregated query. Never loop in Python.

Every money function rounds down to 1,000. Write `round_down_1000(value)` once
and reuse it.

---

## 7. The three interfaces

### 7a. Telegram bot (Aiogram 3, multibot mode)
- ONE Python process serves ALL tenant bots via **multibot / webhook**.
- Webhook endpoint: `POST /webhook/<webhook_secret>` — resolve tenant from the
  secret, NOT from the token (token must never appear in a URL or log).
- Customer flows:
  - `/start` → branded welcome → **request_contact button ONLY** (no manual
    phone entry) → consent prompt → register/claim PendingCashback → show balance.
  - "Balance" → show current points + "usable today" hint.
  - "Redeem" → ask amount → generate OTP (5 min) → show big code to read to
    seller.
  - Auto-notification after every earn/spend: e.g. "✅ 1,500 points added from a
    50,000 purchase. Balance: 12,500. Wrong amount? [Report]".
- A SEPARATE bot (or the same seller web app — see 7b) for sellers; customer bot
  must never expose seller actions.
- Name auto-filled from Telegram `first_name`, editable later.

### 7b. Seller web page (must be FAST — register use)
- Minimal single page. Two big inputs: **check amount** and **customer phone**.
  Enter submits. ~5 seconds total.
- A "No cashback (prescription only)" checkbox.
- A "Redeem points" mode: seller enters the OTP the customer reads out.
- Shows immediate confirmation: earned amount, new balance.
- Seller is scoped to their branch/tenant automatically from their login.
- Works on a desktop browser at the till; no phone required.

### 7c. Admin panel — **Django REST API + separate React frontend**
Backend: Django REST Framework, JWT auth, role-based permissions.
Frontend: React (Vite + TypeScript), talks to the API. Keep them in
`/frontend`. The Django app also keeps the built-in Django admin enabled for
superadmin low-level access, but the primary UI is React.

Superadmin dashboard (top view): table of all bots —
`Bot | Tenant | Customers | Active(30d) | Today's txns | Total liability (sum of balances) | Status`.
Clicking a row drills into that tenant.
Tenant admin: branches, rate setting (bounded by cap), broadcasts, reports.
Reports needed: per-branch earned/spent/outstanding; per-seller txn count &
average check (fraud signal); total outstanding liability; daily earn/spend.

---

## 8. Fraud mitigation (build the cheap layers now)

Sellers enter amounts by hand with no POS integration, so fraud can't be fully
prevented — only made visible and unprofitable. Build these in MVP:

- **Instant customer notification** on every transaction (self-policing) + a
  [Report] button that files to the branch manager.
- **Hard limits:** max check amount (block/flag above `GlobalSettings.max_check_amount`),
  per-seller daily transaction limit, per-customer per-day max redemptions.
- **`seller_id` on every transaction** + a daily per-seller summary to the
  manager.
- The 50% cap + cash-required rule already makes fraud low-value — keep it.

Defer to a later phase: anomaly detection (unusual seller↔customer pair
frequency, above-average check sizes). Leave a `flagged` boolean + a
`suspicion_score` field stub on Transaction so we can fill it later.

---

## 9. Tech stack & conventions

- **Python 3.11+, Django 5, Django REST Framework**
- **Aiogram 3** (multibot webhook mode)
- **PostgreSQL** (money = Decimal, use DB constraints for non-negative amounts)
- **Celery + Redis** (notifications, broadcasts with throttling ≈ 25 msg/sec to
  respect Telegram limits)
- **React (Vite + TypeScript)** in `/frontend`
- **cryptography (Fernet)** for bot token encryption, key from `FERNET_KEY` env
- **pytest + pytest-django** for tests
- **ruff** for lint/format, **mypy** where practical
- **Docker Compose** for local dev (web, worker, db, redis)
- Config via environment variables (django-environ). Never hardcode secrets.
- Timezone: `Asia/Tashkent`. Currency: UZS, integer-ish (2 dp Decimal, round to
  1000).

### Project layout
```
pharmacy-cashback/
  backend/
    config/                 # settings, urls, celery, wsgi/asgi
    apps/
      tenants/              # Tenant, GlobalSettings, Bot, tenant middleware, TenantManager
      accounts/             # User roles, Seller, Manager, auth, JWT
      customers/            # Customer, PendingCashback, OTP
      ledger/               # Transaction, services.py (ALL cashback math), reports
      bot/                  # Aiogram multibot, handlers, webhook view, notification tasks
      broadcasts/           # Broadcast model, sending tasks
      audit/                # AuditLog
      seller_web/           # the fast seller register page (server-rendered is fine here)
    tests/
  frontend/                 # React admin panel (Vite + TS)
  docker-compose.yml
  .env.example
  README.md
```

---

## 10. Definition of done for MVP

- [ ] All 11 domain rules in §2 enforced and unit-tested.
- [ ] Tenant isolation test (§4) passes.
- [ ] Seller can earn + redeem end to end (web page → ledger → bot notification).
- [ ] Customer can register via bot (contact button + consent + claim pending).
- [ ] Multibot: adding a tenant + token in admin auto-sets the webhook, no redeploy.
- [ ] Superadmin dashboard shows cross-tenant table incl. total liability.
- [ ] Tenant admin can set rate (rejected if above cap) and send a broadcast.
- [ ] Reversal flow works and writes an AuditLog entry.
- [ ] Docker Compose brings the whole stack up with one command.
- [ ] README explains setup, env vars, and how to add a tenant/bot.

---

## 11. How to work (instructions to Claude Code)

- Build in the phase order in `IMPLEMENTATION_PLAN.md`. Do not jump ahead.
- After each phase: run tests, run migrations, confirm the app boots, then stop
  and summarize what changed before starting the next phase.
- Write tests alongside code, especially for §2 rules and §4 isolation.
- Prefer a thin view / fat service layer. All cashback math lives in
  `apps/ledger/services.py`.
- Ask before introducing any dependency not listed in §9.
- Never weaken a domain rule to make a test pass. If a rule seems wrong, stop and
  ask.
- Keep secrets in env. Never commit a real bot token or Fernet key.
