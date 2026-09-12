"""Sync orchestration for bot handlers (CLAUDE.md §11: handlers never
compute cashback inline). Every function here is plain synchronous Django/
service-layer code — no aiogram, no async. Handlers in apps/bot/handlers.py
are thin async wrappers that call these via sync_to_async and then send the
Telegram reply. Functions take tenant explicitly rather than relying on the
ambient ContextVar, matching apps/ledger/services.py's convention.
"""

from decimal import Decimal, InvalidOperation

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.bot.i18n import DEFAULT_LANGUAGE, t
from apps.customers.models import OTP, Customer, generate_otp_code
from apps.ledger.models import Transaction
from apps.ledger.services import (
    DailyRedemptionLimitExceededError,
    check_daily_redemption_limit,
    claim_pending_cashback,
    flag_transaction,
    get_balance,
    post_earn_transaction,
)
from apps.tenants.models import GlobalSettings, Tenant


class RedeemAmountError(Exception):
    """The customer's requested redeem amount couldn't be parsed or isn't
    usable right now."""


class RegistrationOwnershipError(Exception):
    """Registration was refused because it would bind an identity that
    already belongs to somebody else — either this phone number is already
    held by a different Telegram account, or this Telegram account already
    holds a different phone number in this tenant.

    str(exc) is a customer-facing, already-translated message (same
    convention as RedeemAmountError above), so apps.bot.handlers can send
    it straight through without knowing which of the two cases fired."""


def normalize_telegram_phone(raw: str) -> str:
    raw = raw.strip()
    return raw if raw.startswith("+") else f"+{raw}"


def get_customer_by_telegram_id(*, tenant: Tenant, telegram_id: int) -> Customer | None:
    return Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=telegram_id).first()


def format_balance_message(customer: Customer) -> str:
    balance = get_balance(customer)
    max_redeem_percent = GlobalSettings.load().max_redeem_percent
    return t(customer.language, "balance_message", balance=balance, percent=max_redeem_percent)


def get_customer_language(*, tenant: Tenant, telegram_id: int) -> str:
    """Used wherever a handler needs the right language for a keyboard/
    prompt before (or without) fetching the full customer — e.g. the redeem
    prompt, or the settings menu. Falls back to DEFAULT_LANGUAGE for an
    unregistered/unknown telegram_id rather than raising, since callers hit
    this in places a registration race could plausibly leave no row yet."""
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    return customer.language if customer is not None else DEFAULT_LANGUAGE


def _assert_account_unclaimed(*, tenant: Tenant, telegram_id: int, language: str) -> None:
    """One Telegram account holds at most one Customer row per tenant —
    that's `unique_customer_telegram_id_per_tenant` (apps/customers/
    models.py). Checked explicitly, before the INSERT, rather than left to
    surface as an IntegrityError: the webhook view swallows unhandled
    exceptions into a 200, so the DB constraint alone would have shown the
    customer nothing at all.

    Reachable legitimately when someone changes the phone number on their
    Telegram account and registers again — they get a clear message
    instead of silence. Not reachable as an attack now that on_contact
    only accepts a Telegram-verified contact.
    """
    already_held = (
        Customer.objects.all_tenants()
        .filter(tenant=tenant, telegram_id=telegram_id)
        .exists()
    )
    if already_held:
        raise RegistrationOwnershipError(t(language, "account_already_registered"))


def _bind_telegram_account(
    *, customer: Customer, tenant: Tenant, telegram_id: int, full_name: str, language: str
) -> None:
    """Apply the ownership rule to an existing (locked) Customer row.

    Three cases, and only three:

    1. `telegram_id IS NULL` — an unclaimed row. These are real: a
       superadmin can add a Customer through Django admin, and
       seed_demo_data creates one (apps/tenants/management/commands/
       seed_demo_data.py). The first Telegram account that proves it owns
       this phone claims it. This is the path that must keep working.
    2. Same `telegram_id` — a repeat/duplicate registration by the row's
       own owner. Idempotent: refresh the display name and backfill
       consent, never touch the binding.
    3. A different, non-null `telegram_id` — the row belongs to somebody
       else. REFUSE. This is the takeover C-2 was about; the old code
       overwrote it here.
    """
    if customer.telegram_id is not None and customer.telegram_id != telegram_id:
        # Deliberately the *requester's* language, not customer.language —
        # the person reading this is whoever just tried to register, and
        # the row's own language preference is the other party's data.
        raise RegistrationOwnershipError(t(language, "phone_already_registered"))

    if customer.telegram_id is None:
        _assert_account_unclaimed(tenant=tenant, telegram_id=telegram_id, language=language)
        customer.telegram_id = telegram_id

    customer.full_name = full_name or customer.full_name
    customer.consent_given_at = customer.consent_given_at or timezone.now()
    customer.save(update_fields=["telegram_id", "full_name", "consent_given_at"])


def handle_registration(
    *,
    tenant: Tenant,
    telegram_id: int,
    phone: str,
    full_name: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """CLAUDE.md §7a: register/claim PendingCashback on /start + contact +
    consent. Returns the fully-formatted reply text.

    `telegram_id` may only ever be bound to a Customer row that is not
    already claimed by a *different* Telegram account. This used to
    overwrite `telegram_id` on any existing row whose id didn't match,
    which meant submitting somebody else's phone number silently moved
    their Customer row — and the whole ledger balance derived from it —
    onto the caller's account. The caller's ownership of the phone is
    established upstream, in apps.bot.handlers.on_contact, and this
    function is what makes that proof stick; see
    _bind_telegram_account below for the three cases.

    Raises RegistrationOwnershipError (customer-facing message) when the
    binding is refused. Nothing is written and no PendingCashback is
    claimed in that case — the whole thing runs in one transaction.
    """
    phone = normalize_telegram_phone(phone)
    with db_transaction.atomic():
        # select_for_update, not a plain read: two consent taps racing on
        # the same phone (one legitimate owner, one attacker; or the same
        # person double-tapping) must be serialized, or both could observe
        # telegram_id IS NULL and both "claim" it. Under READ COMMITTED the
        # second transaction blocks here and then re-reads the row as the
        # first one committed it, so it sees the binding that just landed
        # and refuses instead of overwriting it.
        customer = (
            Customer.objects.all_tenants()
            .select_for_update()
            .filter(tenant=tenant, phone=phone)
            .first()
        )

        if customer is None:
            _assert_account_unclaimed(tenant=tenant, telegram_id=telegram_id, language=language)
            try:
                with db_transaction.atomic():  # savepoint: recover from a raced insert
                    customer = Customer.objects.all_tenants().create(
                        tenant=tenant,
                        phone=phone,
                        telegram_id=telegram_id,
                        full_name=full_name,
                        language=language,
                        consent_given_at=timezone.now(),
                    )
            except IntegrityError:
                # A concurrent registration committed between the SELECT
                # above and this INSERT. Either unique constraint on
                # Customer can be the one that fired, so both are handled
                # rather than assuming it was the phone:
                #
                #  * unique_customer_telegram_id_per_tenant — this same
                #    Telegram account just registered a *different* phone.
                #    Re-running the check turns that into the normal
                #    refusal instead of a DoesNotExist below.
                #  * unique_customer_phone_per_tenant — somebody else took
                #    this phone. Re-read the row under a lock and put it
                #    through the same ownership check the unraced path
                #    takes, so losing the race can never skip it.
                #
                # The inner atomic() above is a savepoint, so the
                # connection is usable again here and these queries run on
                # the still-open outer transaction.
                _assert_account_unclaimed(
                    tenant=tenant, telegram_id=telegram_id, language=language
                )
                customer = (
                    Customer.objects.all_tenants()
                    .select_for_update()
                    .filter(tenant=tenant, phone=phone)
                    .first()
                )
                if customer is None:
                    # Neither constraint explains the failure — surface the
                    # real error rather than masking it as an ownership
                    # refusal the customer can do nothing about.
                    raise
                _bind_telegram_account(
                    customer=customer,
                    tenant=tenant,
                    telegram_id=telegram_id,
                    full_name=full_name,
                    language=language,
                )
        else:
            _bind_telegram_account(
                customer=customer,
                tenant=tenant,
                telegram_id=telegram_id,
                full_name=full_name,
                language=language,
            )

        claimed = claim_pending_cashback(customer=customer)

    lines = [t(customer.language, "registered_success")]
    if claimed:
        total_claimed = sum((row.cashback_earned for row in claimed), Decimal("0"))
        lines.append(t(customer.language, "claimed_amount", amount=total_claimed))
    lines.append(format_balance_message(customer))
    return "\n".join(lines)


def handle_balance_query(*, tenant: Tenant, telegram_id: int) -> str:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return t(DEFAULT_LANGUAGE, "not_registered")
    return format_balance_message(customer)


def customer_is_registered(*, tenant: Tenant, telegram_id: int) -> bool:
    return get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id) is not None


def update_customer_name(*, tenant: Tenant, telegram_id: int, full_name: str) -> Customer | None:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return None
    customer.full_name = full_name
    customer.save(update_fields=["full_name"])
    return customer


def update_customer_language(
    *, tenant: Tenant, telegram_id: int, language: str
) -> Customer | None:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return None
    customer.language = language
    customer.save(update_fields=["language"])
    return customer


def handle_redeem_request(*, tenant: Tenant, telegram_id: int, raw_amount: str) -> str:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return t(DEFAULT_LANGUAGE, "not_registered")
    try:
        otp = _create_redemption_otp(tenant=tenant, customer=customer, raw_amount=raw_amount)
    except RedeemAmountError as exc:
        return str(exc)
    return t(customer.language, "redeem_code", code=otp.code)


def _create_redemption_otp(*, tenant: Tenant, customer: Customer, raw_amount: str) -> OTP:
    try:
        amount = Decimal(raw_amount.strip().replace(",", ""))
    except InvalidOperation as exc:
        raise RedeemAmountError(t(customer.language, "redeem_invalid_number")) from exc
    if amount <= 0:
        raise RedeemAmountError(t(customer.language, "redeem_amount_must_be_positive"))
    if amount > get_balance(customer):
        raise RedeemAmountError(t(customer.language, "redeem_insufficient_balance"))

    # CLAUDE.md §8: reject early here rather than only at the register, so
    # the customer isn't handed a code that's guaranteed to fail. The
    # authoritative check still happens again in redeem_via_otp.
    try:
        check_daily_redemption_limit(tenant=tenant, customer=customer)
    except DailyRedemptionLimitExceededError as exc:
        raise RedeemAmountError(str(exc)) from exc

    return OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, amount_requested=amount, code=generate_otp_code()
    )


def format_notification_text(txn: Transaction) -> str:
    """CLAUDE.md §7a auto-notification text."""
    language = txn.customer.language
    if txn.type == Transaction.Type.REVERSAL:
        parts = [t(language, "notif_reversal")]
    else:
        parts = []
        if txn.cashback_earned > 0:
            parts.append(
                t(
                    language,
                    "notif_earned",
                    check_amount=txn.check_amount,
                    earned=txn.cashback_earned,
                )
            )
        if txn.cashback_spent > 0:
            parts.append(t(language, "notif_spent", spent=txn.cashback_spent))
        if not parts:
            if txn.no_cashback:
                # CLAUDE.md §2 rule 11 (prescription-only checkbox): earned
                # is deliberately 0 here, not a rounding fluke — say so, or
                # the customer just sees an unchanged balance and assumes
                # something broke.
                parts.append(t(language, "notif_no_cashback"))
            else:
                parts.append(t(language, "notif_generic"))
    parts.append(t(language, "notif_balance_suffix", balance=get_balance(txn.customer)))
    return "\n".join(parts)


def handle_receipt_check_data(
    *, tenant: Tenant, customer: Customer, check_data: dict
) -> str | None:
    """Bot-only earn path (apps/bot/tasks.py::process_receipt_photo): a
    customer photographs their fiscal receipt's QR code, the bot reads the
    sale off ofd.soliq.uz (check_data, already trimmed to tin/cash_total/
    card_total/terminal_id/payment_no by _fetch_receipt_via_playwright),
    and this credits cashback the same way a seller's manual entry would —
    via post_earn_transaction, so every domain rule (rate snapshot,
    rounding, hard limits) applies identically, and the receipt's own
    terminal+payment number becomes the idempotency key so re-scanning the
    same receipt is a no-op rather than double-crediting.

    Returns a rejection message to show the customer, or None on success —
    post_earn_transaction's on_commit hook already fires the usual
    notify_transaction Celery task, so a second success message here would
    be redundant."""
    if not tenant.receipt_tin or tenant.receipt_branch_id is None:
        return t(customer.language, "receipt_not_configured")

    if str(check_data.get("tin")) != tenant.receipt_tin:
        return t(customer.language, "receipt_wrong_tenant")

    idempotency_key = f"receipt:{check_data.get('terminal_id')}:{check_data.get('payment_no')}"
    already_used = (
        Transaction.objects.all_tenants()
        .filter(tenant=tenant, idempotency_key=idempotency_key)
        .exists()
    )
    if already_used:
        return t(customer.language, "receipt_already_used")

    cash_total = Decimal(str(check_data.get("cash_total") or 0))
    card_total = Decimal(str(check_data.get("card_total") or 0))
    total = cash_total + card_total
    if total <= 0:
        return t(customer.language, "receipt_fetch_failed")

    post_earn_transaction(
        tenant=tenant,
        branch=tenant.receipt_branch,
        seller=None,
        customer=customer,
        check_amount=total,
        idempotency_key=idempotency_key,
    )
    return None


def handle_report(*, tenant: Tenant, telegram_id: int, transaction_id: int) -> str:
    """CLAUDE.md §8: [Report] button on a notification. Only the customer
    the transaction actually belongs to can flag it — a guessed/foreign
    transaction_id in the callback data is silently rejected rather than
    flagging someone else's transaction."""
    txn = (
        Transaction.objects.all_tenants()
        .filter(pk=transaction_id, tenant=tenant)
        .select_related("customer")
        .first()
    )
    if txn is None or txn.customer.telegram_id != telegram_id:
        return t(DEFAULT_LANGUAGE, "report_invalid")

    flag_transaction(transaction_id=txn.pk)
    return t(txn.customer.language, "report_thanks")
