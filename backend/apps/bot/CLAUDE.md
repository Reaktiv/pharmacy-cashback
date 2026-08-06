# Telegram bot (Aiogram 3, multibot mode)

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
- A SEPARATE bot (or the same seller web app — see `backend/apps/seller_web/CLAUDE.md`)
  for sellers; customer bot must never expose seller actions.
- Name auto-filled from Telegram `first_name`, editable later.
