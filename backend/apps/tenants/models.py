import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.context import get_current_tenant, tenant_check_bypassed
from apps.tenants.crypto import decrypt_token, encrypt_token


class TenantContextError(RuntimeError):
    """No tenant is bound to the current context.

    CLAUDE.md §4: a missing tenant filter is a data breach, so the default
    manager fails loudly instead of silently returning nothing. Cross-tenant
    reads (superadmin code only) must opt in explicitly via `.all_tenants()`.
    """


class TenantManager(models.Manager):
    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant is None:
            if tenant_check_bypassed():
                return super().get_queryset()
            raise TenantContextError(
                f"{self.model.__name__} query attempted with no tenant bound to the "
                f"current context. Use `{self.model.__name__}.objects.all_tenants()` "
                "for explicit cross-tenant access (superadmin code only)."
            )
        return super().get_queryset().filter(tenant=tenant)

    def all_tenants(self):
        """Escape hatch: unfiltered queryset. Superadmin code only — never use
        this to build a response that a tenant-scoped user will see."""
        return super().get_queryset()


class TenantScopedModel(models.Model):
    """Abstract base for every tenant-owned table (CLAUDE.md §4).

    `objects` is tenant-filtered and is what application code should use.
    `base_objects` is unfiltered and is wired as Meta.base_manager_name so
    Django's own internals (refresh_from_db, cascades, fixture loading) don't
    get blocked by the tenant-context requirement — those are framework
    plumbing, not a data-leak surface.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)

    objects = TenantManager()
    base_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "base_objects"


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


class GlobalSettings(models.Model):
    """Singleton, superadmin-only (CLAUDE.md §5). Use GlobalSettings.load()."""

    max_cashback_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("15.00")
    )
    max_redeem_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("50.00")
    )
    max_check_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("2000000.00")
    )
    max_daily_redemptions_per_customer = models.PositiveIntegerField(default=5)

    class Meta:
        verbose_name = "Global settings"
        verbose_name_plural = "Global settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("GlobalSettings is a singleton and cannot be deleted.")

    @classmethod
    def load(cls) -> "GlobalSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Global settings"


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    cashback_rate = models.DecimalField(max_digits=5, decimal_places=2)
    min_redeem_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("20000.00")
    )
    points_expiry_days = models.PositiveIntegerField(null=True, blank=True, default=None)
    default_daily_txn_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Default per-seller daily transaction cap for this tenant. "
        "Null = unlimited. A Seller.daily_txn_limit, when set, overrides this.",
    )
    broadcast_quota = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Max broadcasts a tenant can send per calendar month, shared "
        "across all its tenant_admin logins. Null = unlimited.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        cap = GlobalSettings.load().max_cashback_rate
        if self.cashback_rate is not None and self.cashback_rate > cap:
            raise ValidationError(
                {
                    "cashback_rate": (
                        f"Cashback rate ({self.cashback_rate}%) exceeds the global "
                        f"cap of {cap}%."
                    )
                }
            )

    def __str__(self):
        return self.name


class Bot(TenantScopedModel):
    """One row per tenant's Telegram bot (CLAUDE.md §5). One-to-one for MVP."""

    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="bot")
    token_encrypted = models.CharField(max_length=255)
    username = models.CharField(max_length=64)
    webhook_secret = models.CharField(max_length=64, unique=True, default=generate_webhook_secret)
    is_active = models.BooleanField(default=True)

    def set_token(self, raw_token: str) -> None:
        self.token_encrypted = encrypt_token(raw_token)

    def get_token(self) -> str:
        return decrypt_token(self.token_encrypted)

    def __str__(self):
        return self.username
