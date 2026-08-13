"""Sync orchestration for bot handlers (CLAUDE.md §11: handlers never
compute cashback inline). Every function here is plain synchronous Django/
service-layer code — no aiogram, no async. Handlers in apps/bot/handlers.py
are thin async wrappers that call these via sync_to_async and then send the
Telegram reply. Functions take tenant explicitly rather than relying on the
ambient ContextVar, matching apps/ledger/services.py's convention.
"""

from decimal import Decimal, InvalidOperation

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
)
from apps.tenants.models import GlobalSettings, Tenant


class RedeemAmountError(Exception):
    """The customer's requested redeem amount couldn't be parsed or isn't
    usable right now."""


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


def handle_registration(
    *,
    tenant: Tenant,
    telegram_id: int,
    phone: str,
    full_name: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """CLAUDE.md §7a: register/claim PendingCashback on /start + contact +
    consent. Returns the fully-formatted reply text."""
    phone = normalize_telegram_phone(phone)
    customer, created = Customer.objects.all_tenants().get_or_create(
        tenant=tenant,
        phone=phone,
        defaults={
            "telegram_id": telegram_id,
            "full_name": full_name,
            "language": language,
            "consent_given_at": timezone.now(),
        },
    )
    if not created and customer.telegram_id != telegram_id:
        customer.telegram_id = telegram_id
        customer.full_name = full_name or customer.full_name
        customer.consent_given_at = customer.consent_given_at or timezone.now()
        customer.save(update_fields=["telegram_id", "full_name", "consent_given_at"])

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
