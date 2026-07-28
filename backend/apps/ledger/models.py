from decimal import Decimal

from django.db import models

from apps.tenants.models import TenantScopedModel


class Transaction(TenantScopedModel):
    """THE LEDGER (CLAUDE.md §5). Balance is always derived from this table —
    see apps.ledger.services.get_balance. Rows are never deleted or have
    their amounts updated after posting (CLAUDE.md §2 rule 7); corrections
    are reversal rows created by apps.ledger.services.post_reversal.

    flagged is set by apps.ledger.services.flag_transaction when a customer
    taps [Report] on a notification (CLAUDE.md §8). suspicion_score stays a
    stub — automated scoring is explicitly deferred to a future anomaly-
    detection phase, not built here.
    """

    class Type(models.TextChoices):
        EARN = "earn", "Earn"
        SPEND = "spend", "Spend"
        REVERSAL = "reversal", "Reversal"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVERSED = "reversed", "Reversed"

    branch = models.ForeignKey(
        "accounts.Branch", on_delete=models.PROTECT, related_name="transactions"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="transactions"
    )
    seller = models.ForeignKey(
        "accounts.Seller",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

    check_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cashback_earned = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    cashback_spent = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    cash_paid = models.DecimalField(max_digits=12, decimal_places=2)
    cashback_rate = models.DecimalField(max_digits=5, decimal_places=2)

    type = models.CharField(max_length=10, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    reverses = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_by",
    )
    no_cashback = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=255)

    flagged = models.BooleanField(default=False)
    suspicion_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"], name="unique_txn_idempotency_per_tenant"
            ),
            models.CheckConstraint(
                check=models.Q(check_amount__gte=0), name="txn_check_amount_gte_0"
            ),
            models.CheckConstraint(
                check=models.Q(cashback_earned__gte=0), name="txn_cashback_earned_gte_0"
            ),
            models.CheckConstraint(
                check=models.Q(cashback_spent__gte=0), name="txn_cashback_spent_gte_0"
            ),
            models.CheckConstraint(check=models.Q(cash_paid__gte=0), name="txn_cash_paid_gte_0"),
        ]

    def __str__(self):
        return f"{self.type} {self.check_amount} ({self.customer_id})"
