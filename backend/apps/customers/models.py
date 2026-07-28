import secrets
from datetime import timedelta

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.tenants.models import TenantScopedModel

phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Phone must be E.164 format, e.g. +998901234567.",
)


class Customer(TenantScopedModel):
    telegram_id = models.BigIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    full_name = models.CharField(max_length=255, blank=True)
    consent_given_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "phone"], name="unique_customer_phone_per_tenant"
            ),
            models.UniqueConstraint(
                fields=["tenant", "telegram_id"],
                condition=models.Q(telegram_id__isnull=False),
                name="unique_customer_telegram_id_per_tenant",
            ),
        ]

    def __str__(self):
        return self.full_name or self.phone


def default_pending_cashback_expiry():
    return timezone.now() + timedelta(days=30)


class PendingCashback(TenantScopedModel):
    """CLAUDE.md §5: holds earned cashback for a phone number not yet
    registered in the bot. Claimed into the customer's ledger on
    registration (Phase 5).

    source_transaction is nullable: a Transaction requires a Customer, and
    the whole point of this model is handling a phone with no Customer yet
    (Phase 4's seller-web earn flow) — so at creation time there's nothing
    to point to. It may get linked later once the real earn Transaction is
    posted at claim time.

    idempotency_key: not in CLAUDE.md §5's literal field list, but the
    Transaction model's idempotency protection (Phase 3) doesn't cover this
    path, and IMPLEMENTATION_PLAN Phase 4 explicitly requires double-submit
    protection here too — a double-click on the seller-web earn form for an
    unregistered phone would otherwise double-credit it.

    branch: also not in §5's literal field list. Transaction.branch is a
    required FK, so apps.ledger.services.claim_pending_cashback (Phase 5)
    needs to know which branch originated each pending row to correctly
    attribute the real earn Transaction it creates at claim time — captured
    here at seller-web earn time (Phase 4's post_earn_by_phone already has
    it as a parameter).
    """

    phone = models.CharField(max_length=20, validators=[phone_validator])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    branch = models.ForeignKey(
        "accounts.Branch", on_delete=models.PROTECT, related_name="pending_cashbacks"
    )
    source_transaction = models.ForeignKey(
        "ledger.Transaction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pending_cashbacks",
    )
    expires_at = models.DateTimeField(default=default_pending_cashback_expiry)
    claimed = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0), name="pending_cashback_amount_gte_0"
            ),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="unique_pending_cashback_idempotency_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.phone}: {self.amount}"


def default_otp_expiry():
    return timezone.now() + timedelta(minutes=5)


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class OTP(TenantScopedModel):
    """CLAUDE.md §5: redemption code. Single-use, 5-minute expiry."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6, default=generate_otp_code)
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    expires_at = models.DateTimeField(default=default_otp_expiry)
    used = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_requested__gte=0), name="otp_amount_requested_gte_0"
            ),
        ]

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.customer_id}:{self.code}"
