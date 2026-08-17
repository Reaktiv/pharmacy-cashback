"""ALL cashback math lives here (CLAUDE.md §6 / §11 "how to work"). Views and
bot handlers must never compute cashback inline — they call these functions.

Every function here takes tenant/customer explicitly and queries via
`.all_tenants()` with an explicit tenant filter, rather than relying on the
ambient tenant ContextVar. Reason: these functions must work identically
whether called from a web view (where TenantMiddleware has bound a tenant),
a Celery task, or a bot webhook handler (Phase 5) — none of which are
guaranteed to have that context set.
"""

from decimal import ROUND_DOWN, Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.accounts.models import Seller
from apps.accounts.ratelimit import release_rate_limit_slot, reserve_rate_limit_slot
from apps.customers.models import OTP, Customer, PendingCashback
from apps.ledger.models import Transaction
from apps.tenants.models import GlobalSettings, Tenant

# A live OTP is a 6-digit code guessable within its own 5-minute expiry if
# attempts go unbounded — this caps how many redeem attempts one seller
# account can make in that window, regardless of whether each guess hits.
OTP_REDEEM_ATTEMPT_LIMIT = 10
OTP_REDEEM_ATTEMPT_WINDOW_SECONDS = 300


def _notify_transaction(transaction_id: int) -> None:
    """Fires the Phase 5 bot notification after the enclosing transaction
    commits. Local import: apps.bot depends on apps.ledger (Transaction),
    so importing apps.bot.tasks at module load time here would be circular.
    """
    from apps.bot.tasks import notify_transaction

    notify_transaction.delay(transaction_id)


class InsufficientBalanceError(Exception):
    """A transaction would spend more cashback than the customer's current
    ledger-derived balance covers."""


class InvalidOTPError(Exception):
    """An OTP code is missing, already used, expired, or for the wrong
    tenant."""


class MaxCheckAmountExceededError(Exception):
    """check_amount exceeds GlobalSettings.max_check_amount (CLAUDE.md §8)."""


class DailyTransactionLimitExceededError(Exception):
    """A seller has hit their daily transaction cap (CLAUDE.md §8)."""


class DailyRedemptionLimitExceededError(Exception):
    """A customer has hit their daily redemption count cap (CLAUDE.md §8)."""


def _effective_daily_txn_limit(seller) -> int | None:
    if seller is None:
        return None
    if seller.daily_txn_limit is not None:
        return seller.daily_txn_limit
    return seller.tenant.default_daily_txn_limit


def _enforce_hard_limits(*, tenant: Tenant, seller, check_amount: Decimal) -> None:
    """CLAUDE.md §8 hard limits: max check amount + per-seller daily
    transaction count. Both are hard blocks with clear errors — Phase 6's
    done-criterion is "limits are enforced with clear errors."
    """
    max_check_amount = GlobalSettings.load().max_check_amount
    if check_amount > max_check_amount:
        raise MaxCheckAmountExceededError(
            f"Chek summasi ({check_amount}) platforma uchun belgilangan maksimal "
            f"miqdordan ({max_check_amount}) oshib ketdi."
        )

    limit = _effective_daily_txn_limit(seller)
    if limit is not None:
        count_today = (
            Transaction.objects.all_tenants()
            .filter(tenant=tenant, seller=seller, created_at__date=timezone.localdate())
            .count()
        )
        if count_today >= limit:
            raise DailyTransactionLimitExceededError(
                f"Kunlik tranzaksiya limiti ({limit}) ga yetdi."
            )


def check_daily_redemption_limit(*, tenant: Tenant, customer: Customer) -> None:
    """CLAUDE.md §8: per-customer per-day max redemptions. Not prefixed
    with an underscore — apps.bot.services calls this too, to reject an
    over-limit request when the OTP is created rather than only failing
    later at the register.
    """
    limit = GlobalSettings.load().max_daily_redemptions_per_customer
    count_today = (
        Transaction.objects.all_tenants()
        .filter(
            tenant=tenant,
            customer=customer,
            cashback_spent__gt=0,
            created_at__date=timezone.localdate(),
        )
        .count()
    )
    if count_today >= limit:
        raise DailyRedemptionLimitExceededError(
            f"Kunlik ballarni ishlatish limiti ({limit} marta) ga yetdi."
        )


def round_down_som(value: Decimal) -> Decimal:
    """CLAUDE.md §2 rule 9: round down to the nearest whole so'm (no tiyin/
    small change). Previously this rounded down to the nearest 1,000 UZS,
    which silently zeroed out any cashback computed from a sub-1% rate
    (e.g. 0.1%, 0.01%) on all but very large checks — rounding to whole
    so'm instead keeps those small rates meaningful while still dropping
    fractional tiyin, which don't circulate."""
    if value < 0:
        raise ValueError("round_down_som expects a non-negative amount")
    return value.to_integral_value(rounding=ROUND_DOWN).quantize(Decimal("0.01"))


def calculate_earn(check_amount: Decimal, cash_paid: Decimal, rate: Decimal) -> Decimal:
    """CLAUDE.md §6. `check_amount` is accepted for signature parity (and any
    future category-rate work per §2 rule 11) but the formula only uses
    cash_paid — that's rule 2: never earn on the cashback-paid portion.
    """
    return round_down_som(cash_paid * rate / Decimal("100"))


def calculate_redemption(
    check_amount: Decimal, requested: Decimal, customer_balance: Decimal, tenant: Tenant
) -> Decimal:
    """CLAUDE.md §6 rules 3 and 8."""
    if check_amount < tenant.min_redeem_amount:
        return Decimal("0")

    max_redeem_percent = GlobalSettings.load().max_redeem_percent
    cap = check_amount * (max_redeem_percent / Decimal("100"))
    allowed = min(requested, cap, customer_balance)
    if allowed <= 0:
        return Decimal("0")
    return round_down_som(allowed)


def get_balance(customer: Customer) -> Decimal:
    """CLAUDE.md §2 rule 6 / §6: balance is always ledger-derived, computed
    in a single aggregate query — never looped in Python.

    Deliberately sums over ALL of the customer's transactions, not just
    status='active' ones. A reversed original's row is never excluded from
    the sum: like real double-entry bookkeeping, a correction is always an
    *additional* offsetting entry (the reversal row, with earned/spent
    swapped — see post_reversal), never a removal of the original from the
    running total. Filtering out reversed-status rows here as well would
    double-apply the correction (the swapped reversal row would cancel the
    original a second time). `status` marks a row as corrected for
    audit/display and blocks double-reversal — it is not a balance filter.
    """
    aggregates = (
        Transaction.objects.all_tenants()
        .filter(tenant_id=customer.tenant_id, customer=customer)
        .aggregate(earned=Sum("cashback_earned"), spent=Sum("cashback_spent"))
    )
    earned = aggregates["earned"] or Decimal("0")
    spent = aggregates["spent"] or Decimal("0")
    return earned - spent


def post_earn_transaction(
    *,
    tenant: Tenant,
    branch,
    seller,
    customer: Customer,
    check_amount: Decimal,
    cashback_spent: Decimal = Decimal("0"),
    no_cashback: bool = False,
    idempotency_key: str,
) -> Transaction:
    """CLAUDE.md §6. Always creates a type='earn' row — a row may carry both
    an earned and a spent amount for the same register action (§5)."""
    with db_transaction.atomic():
        existing = (
            Transaction.objects.all_tenants()
            .filter(tenant=tenant, idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            return existing

        locked_customer = (
            Customer.objects.all_tenants().select_for_update().get(pk=customer.pk, tenant=tenant)
        )

        _enforce_hard_limits(tenant=tenant, seller=seller, check_amount=check_amount)

        if cashback_spent > 0:
            balance = get_balance(locked_customer)
            if cashback_spent > balance:
                raise InsufficientBalanceError(
                    f"Mijoz balansi ({balance}) so'ralgan {cashback_spent} balldan kam."
                )

        cash_paid = check_amount - cashback_spent
        earned = (
            Decimal("0")
            if no_cashback
            else calculate_earn(check_amount, cash_paid, tenant.cashback_rate)
        )

        try:
            with db_transaction.atomic():  # savepoint: recover cleanly from a raced duplicate
                txn = Transaction.objects.all_tenants().create(
                    tenant=tenant,
                    branch=branch,
                    customer=locked_customer,
                    seller=seller,
                    check_amount=check_amount,
                    cashback_earned=earned,
                    cashback_spent=cashback_spent,
                    cash_paid=cash_paid,
                    cashback_rate=tenant.cashback_rate,
                    type=Transaction.Type.EARN,
                    status=Transaction.Status.ACTIVE,
                    no_cashback=no_cashback,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            return Transaction.objects.all_tenants().get(
                tenant=tenant, idempotency_key=idempotency_key
            )

        db_transaction.on_commit(lambda: _notify_transaction(txn.pk))
        return txn


def post_reversal(*, original_txn: Transaction, actor) -> Transaction:
    """CLAUDE.md §2 rule 7 / §6.

    "Negating" a transaction can't mean a literal negative amount — earned
    and spent are both DB-constrained to be >= 0. Instead the reversal row
    swaps them: reversal.earned = original.spent, reversal.spent =
    original.earned. get_balance sums over ALL of a customer's transactions
    unconditionally (see its docstring), so this swapped row is exactly the
    negation of what the original contributed — the original itself stays
    in the sum untouched, marked status='reversed' purely as an audit/
    double-reversal-guard flag, not excluded from the balance.

    `actor` is accepted for signature parity — AuditLog writing is
    explicitly Phase 8 scope (IMPLEMENTATION_PLAN.md), not wired yet.
    """
    with db_transaction.atomic():
        locked_original = Transaction.objects.all_tenants().select_for_update().get(
            pk=original_txn.pk
        )
        if locked_original.status == Transaction.Status.REVERSED:
            raise ValueError(f"Transaction {locked_original.pk} is already reversed.")

        locked_customer = (
            Customer.objects.all_tenants()
            .select_for_update()
            .get(pk=locked_original.customer_id, tenant=locked_original.tenant_id)
        )

        reversal = Transaction.objects.all_tenants().create(
            tenant=locked_original.tenant,
            branch=locked_original.branch,
            customer=locked_customer,
            seller=None,
            check_amount=locked_original.check_amount,
            cashback_earned=locked_original.cashback_spent,
            cashback_spent=locked_original.cashback_earned,
            cash_paid=Decimal("0"),
            cashback_rate=locked_original.cashback_rate,
            type=Transaction.Type.REVERSAL,
            status=Transaction.Status.ACTIVE,
            no_cashback=False,
            reverses=locked_original,
            idempotency_key=f"reversal:{locked_original.pk}",
        )

        locked_original.status = Transaction.Status.REVERSED
        locked_original.save(update_fields=["status"])

    db_transaction.on_commit(lambda: _notify_transaction(reversal.pk))
    return reversal


def post_earn_by_phone(
    *,
    tenant: Tenant,
    branch,
    seller,
    phone: str,
    check_amount: Decimal,
    no_cashback: bool = False,
    idempotency_key: str,
) -> Transaction | PendingCashback | None:
    """Seller-web earn flow (IMPLEMENTATION_PLAN.md Phase 4): looks up the
    customer by phone. If none exists yet, there's no Customer to attach a
    Transaction to, so this records a PendingCashback instead — it becomes
    a real earn Transaction once the customer registers via the bot
    (Phase 5). Returns None if there was nothing to record (no_cashback, or
    a zero-cash check).
    """
    customer = Customer.objects.all_tenants().filter(tenant=tenant, phone=phone).first()
    if customer is not None:
        return post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=check_amount,
            no_cashback=no_cashback,
            idempotency_key=idempotency_key,
        )

    _enforce_hard_limits(tenant=tenant, seller=seller, check_amount=check_amount)

    # No existing balance to spend against, so cash_paid is the full check.
    earned = (
        Decimal("0")
        if no_cashback
        else calculate_earn(check_amount, check_amount, tenant.cashback_rate)
    )
    if earned <= 0:
        return None

    existing = (
        PendingCashback.objects.all_tenants()
        .filter(tenant=tenant, idempotency_key=idempotency_key)
        .first()
    )
    if existing is not None:
        return existing

    try:
        with db_transaction.atomic():  # savepoint: recover cleanly from a raced duplicate
            return PendingCashback.objects.all_tenants().create(
                tenant=tenant,
                phone=phone,
                amount=earned,
                branch=branch,
                source_transaction=None,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        return PendingCashback.objects.all_tenants().get(
            tenant=tenant, idempotency_key=idempotency_key
        )


def redeem_via_otp(
    *,
    tenant: Tenant,
    branch,
    seller,
    otp_code: str,
    check_amount: Decimal,
    no_cashback: bool = False,
    idempotency_key: str,
) -> Transaction:
    """Seller-web redeem flow. The OTP is created by the customer's bot
    (Phase 5) carrying their requested redemption amount; here we validate
    it, compute what's actually allowed, and post it as a spend — alongside
    any earn on the residual cash-paid portion, via the same
    post_earn_transaction used by the plain earn flow (§5: a single register
    action can both spend and earn).

    Rate-limited against OTP guessing (CLAUDE.md §8), but only failed
    attempts count — reserve_rate_limit_slot() atomically reserves a slot
    up front (race-safe under concurrent requests — audit finding M-1,
    same fix as TenantAwareTokenObtainPairView's login throttle) and
    release_rate_limit_slot() gives it back once the `else` block below
    confirms the attempt actually succeeded. A busy seller doing many
    *valid* redemptions in a row must never get throttled for it; only
    wrong-code/insufficient-balance guesses should burn down the allowance.
    """
    otp_attempt_key = f"otp_redeem_attempts:{seller.id}"
    reserve_rate_limit_slot(
        key=otp_attempt_key,
        limit=OTP_REDEEM_ATTEMPT_LIMIT,
        window_seconds=OTP_REDEEM_ATTEMPT_WINDOW_SECONDS,
    )

    try:
        with db_transaction.atomic():
            otp = (
                OTP.objects.all_tenants()
                .select_for_update()
                .filter(tenant=tenant, code=otp_code, used=False)
                .first()
            )
            if otp is None:
                raise InvalidOTPError(
                    "OTP kod topilmadi, allaqachon ishlatilgan yoki boshqa tarmoqqa tegishli."
                )
            if otp.is_expired():
                raise InvalidOTPError("OTP kod muddati tugagan.")

            customer = Customer.objects.all_tenants().get(pk=otp.customer_id, tenant=tenant)
            check_daily_redemption_limit(tenant=tenant, customer=customer)
            balance = get_balance(customer)
            allowed = calculate_redemption(check_amount, otp.amount_requested, balance, tenant)
            if allowed <= 0:
                raise InvalidOTPError(
                    "Ishlatib bo'lmaydi: chek summasi tarmoq minimumidan past, "
                    "yoki balans yetarli emas."
                )

            txn = post_earn_transaction(
                tenant=tenant,
                branch=branch,
                seller=seller,
                customer=customer,
                check_amount=check_amount,
                cashback_spent=allowed,
                no_cashback=no_cashback,
                idempotency_key=idempotency_key,
            )

            otp.used = True
            otp.save(update_fields=["used"])
    except (InvalidOTPError, InsufficientBalanceError):
        # Reservation already counted this attempt — nothing further to do;
        # the raise below is what makes this a "failure" that keeps its
        # slot spent, as opposed to the success path, which explicitly
        # gives its slot back.
        raise
    else:
        release_rate_limit_slot(key=otp_attempt_key)

    return txn


def claim_pending_cashback(*, customer: Customer) -> list[Transaction]:
    """CLAUDE.md §5 PendingCashback: called once when a customer registers
    via the bot with a matching phone (Phase 5). Moves every unexpired,
    unclaimed PendingCashback for that phone into a real earn Transaction,
    crediting the exact amount already computed at seller-web earn time —
    not recomputed here, since the rate/cash_paid math already happened
    then. Each row uses its own recorded branch, since a customer may have
    accrued pending cashback at more than one branch before registering.

    Deliberately does not fire the usual bot notification per transaction
    (contrast post_earn_transaction/post_reversal) — the caller is always
    the registration flow itself, which already sends the customer one
    consolidated "you're registered, here's what got credited" message in
    the same interaction; a stream of separate notifications on top would
    be redundant.
    """
    with db_transaction.atomic():
        locked_customer = (
            Customer.objects.all_tenants()
            .select_for_update()
            .get(pk=customer.pk, tenant_id=customer.tenant_id)
        )
        pending_rows = list(
            PendingCashback.objects.all_tenants()
            .select_for_update()
            .filter(
                tenant_id=locked_customer.tenant_id,
                phone=locked_customer.phone,
                claimed=False,
                expires_at__gt=timezone.now(),
            )
        )

        claimed_transactions = []
        for pending in pending_rows:
            txn = Transaction.objects.all_tenants().create(
                tenant_id=pending.tenant_id,
                branch=pending.branch,
                customer=locked_customer,
                seller=None,
                check_amount=pending.amount,
                cashback_earned=pending.amount,
                cashback_spent=Decimal("0"),
                cash_paid=pending.amount,
                cashback_rate=locked_customer.tenant.cashback_rate,
                type=Transaction.Type.EARN,
                status=Transaction.Status.ACTIVE,
                no_cashback=False,
                idempotency_key=f"pending-claim:{pending.pk}",
            )
            pending.claimed = True
            pending.source_transaction = txn
            pending.save(update_fields=["claimed", "source_transaction"])
            claimed_transactions.append(txn)

    return claimed_transactions


def flag_transaction(*, transaction_id: int) -> Transaction:
    """CLAUDE.md §8: the [Report] button on a bot notification (apps/bot's
    on_report handler) calls this, making the transaction visible for
    manager review. Manager-facing UI to browse flagged transactions is
    Phase 7 (no branch-manager web panel exists yet) — this just makes the
    data queryable, and Django admin already lists it.
    """
    txn = Transaction.objects.all_tenants().get(pk=transaction_id)
    txn.flagged = True
    txn.save(update_fields=["flagged"])
    return txn


def get_daily_seller_summary(*, branch, date=None) -> list[dict]:
    """CLAUDE.md §8: per-seller transaction count / totals / average check
    for one branch on one day (default today) — feeds the daily summary
    task in apps/ledger/tasks.py."""
    target_date = date or timezone.localdate()
    rows = (
        Transaction.objects.all_tenants()
        .filter(branch=branch, seller__isnull=False, created_at__date=target_date)
        .values("seller_id")
        .annotate(
            txn_count=Count("id"),
            total_earned=Sum("cashback_earned"),
            total_spent=Sum("cashback_spent"),
            avg_check=Avg("check_amount"),
        )
        .order_by("seller_id")
    )
    sellers_by_id = {
        seller.pk: seller
        for seller in Seller.objects.all_tenants().filter(
            pk__in=[row["seller_id"] for row in rows]
        )
    }
    return [
        {
            "seller": sellers_by_id.get(row["seller_id"]),
            "txn_count": row["txn_count"],
            "total_earned": row["total_earned"] or Decimal("0"),
            "total_spent": row["total_spent"] or Decimal("0"),
            "avg_check": row["avg_check"] or Decimal("0"),
        }
        for row in rows
    ]
