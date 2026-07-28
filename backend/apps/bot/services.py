"""Sync orchestration for bot handlers (CLAUDE.md §11: handlers never
compute cashback inline). Every function here is plain synchronous Django/
service-layer code — no aiogram, no async. Handlers in apps/bot/handlers.py
are thin async wrappers that call these via sync_to_async and then send the
Telegram reply. Functions take tenant explicitly rather than relying on the
ambient ContextVar, matching apps/ledger/services.py's convention.
"""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

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
    return (
        f"Your balance: {balance} points.\n"
        f"You can use up to {max_redeem_percent}% of any purchase total."
    )


def handle_registration(
    *, tenant: Tenant, telegram_id: int, phone: str, full_name: str
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
            "consent_given_at": timezone.now(),
        },
    )
    if not created and customer.telegram_id != telegram_id:
        customer.telegram_id = telegram_id
        customer.full_name = full_name or customer.full_name
        customer.consent_given_at = customer.consent_given_at or timezone.now()
        customer.save(update_fields=["telegram_id", "full_name", "consent_given_at"])

    claimed = claim_pending_cashback(customer=customer)

    lines = ["You're registered! 🎉"]
    if claimed:
        total_claimed = sum((t.cashback_earned for t in claimed), Decimal("0"))
        lines.append(f"We credited {total_claimed} pending points from earlier purchases.")
    lines.append(format_balance_message(customer))
    return "\n".join(lines)


def handle_balance_query(*, tenant: Tenant, telegram_id: int) -> str:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return "You're not registered yet — send /start to begin."
    return format_balance_message(customer)


def customer_is_registered(*, tenant: Tenant, telegram_id: int) -> bool:
    return get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id) is not None


def handle_redeem_request(*, tenant: Tenant, telegram_id: int, raw_amount: str) -> str:
    customer = get_customer_by_telegram_id(tenant=tenant, telegram_id=telegram_id)
    if customer is None:
        return "You're not registered yet — send /start to begin."
    try:
        otp = _create_redemption_otp(tenant=tenant, customer=customer, raw_amount=raw_amount)
    except RedeemAmountError as exc:
        return str(exc)
    return f"Your code: {otp.code}\nShow this to the cashier. It expires in 5 minutes."


def _create_redemption_otp(*, tenant: Tenant, customer: Customer, raw_amount: str) -> OTP:
    try:
        amount = Decimal(raw_amount.strip().replace(",", ""))
    except InvalidOperation as exc:
        raise RedeemAmountError("Please send a valid number.") from exc
    if amount <= 0:
        raise RedeemAmountError("Amount must be greater than zero.")
    if amount > get_balance(customer):
        raise RedeemAmountError("You don't have that many points.")

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
    if txn.type == Transaction.Type.REVERSAL:
        parts = ["⚠️ A previous transaction was corrected."]
    else:
        parts = []
        if txn.cashback_earned > 0:
            parts.append(
                f"✅ {txn.cashback_earned} points added from a {txn.check_amount} purchase."
            )
        if txn.cashback_spent > 0:
            parts.append(f"✅ {txn.cashback_spent} points spent.")
        if not parts:
            parts.append("Your purchase was recorded.")
    parts.append(f"Balance: {get_balance(txn.customer)}.")
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
        return "Sorry, that report could not be processed."

    flag_transaction(transaction_id=txn.pk)
    return "Thanks — this has been noted. A manager will review it."
