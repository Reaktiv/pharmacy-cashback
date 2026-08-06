from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Tenant, TenantScopedModel


class UserProfile(models.Model):
    """Links a Django User to a role + tenant/branch scope (CLAUDE.md §3).

    Deliberately NOT a TenantScopedModel: TenantMiddleware reads
    `request.user.profile` to *establish* the tenant context in the first
    place, so this lookup must work before any tenant is bound yet. It uses
    the plain default manager — every tenant-owned business model uses
    TenantManager instead.
    """

    class Role(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        SUPERADMIN = "superadmin", "Superadmin"
        TENANT_ADMIN = "tenant_admin", "Tenant Admin"
        BRANCH_MANAGER = "branch_manager", "Branch Manager"
        SELLER = "seller", "Seller"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.UNASSIGNED)
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="user_profiles"
    )
    branch = models.ForeignKey(
        "accounts.Branch",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="user_profiles",
    )

    def clean(self):
        super().clean()
        if self.role in (self.Role.SUPERADMIN, self.Role.UNASSIGNED):
            if self.tenant_id or self.branch_id:
                raise ValidationError(
                    "A superadmin/unassigned profile must not be scoped to a tenant or branch."
                )
        elif self.role == self.Role.TENANT_ADMIN:
            if not self.tenant_id:
                raise ValidationError({"tenant": "Tenant admin profiles require a tenant."})
            if self.branch_id:
                raise ValidationError(
                    {"branch": "Tenant admin profiles must not be scoped to a single branch."}
                )
        else:  # BRANCH_MANAGER, SELLER
            if not self.tenant_id or not self.branch_id:
                raise ValidationError(
                    "Branch manager / seller profiles require both a tenant and a branch."
                )
            if self.branch.tenant_id != self.tenant_id:
                raise ValidationError({"branch": "Branch must belong to the same tenant."})
            if self.role == self.Role.SELLER and not hasattr(self.user, "seller_profile"):
                # Seller carries the branch/phone/full_name a seller role
                # actually needs, which this profile alone can't supply — so
                # provisioning always flows Seller -> profile (see
                # apps.accounts.signals.sync_profile_with_seller), never the
                # other way. Block the role flip until that row exists so a
                # profile can never claim to be a seller it isn't.
                raise ValidationError(
                    "A seller profile requires a linked Seller record — create the "
                    "Seller (branch, phone, full name) via the Sellers admin first; "
                    "it sets this role automatically."
                )

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Branch(TenantScopedModel):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Seller(TenantScopedModel):
    """CLAUDE.md §5.

    tenant/branch are duplicated from the linked user's UserProfile (checked
    in clean()) rather than derived through it, because Transaction.seller
    (Phase 3) needs to filter/report on sellers directly without a join
    through accounts. UserProfile stays the canonical scope.
    """

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="sellers")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile"
    )
    phone = models.CharField(max_length=20)
    full_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    daily_txn_limit = models.PositiveIntegerField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.branch_id and self.tenant_id and self.branch.tenant_id != self.tenant_id:
            raise ValidationError({"branch": "Branch must belong to the same tenant."})
        # Only enforce this once the profile is already a seller elsewhere
        # scoped: a brand-new Seller for a still-UNASSIGNED user is the
        # normal provisioning path (apps.accounts.signals.sync_profile_with_seller
        # sets the profile's role/tenant/branch to match right after this
        # save), so it must not be blocked here.
        profile = getattr(self.user, "profile", None)
        if (
            profile is not None
            and profile.role == UserProfile.Role.SELLER
            and (profile.tenant_id != self.tenant_id or profile.branch_id != self.branch_id)
        ):
            raise ValidationError(
                "Seller.tenant/branch must match the linked user's UserProfile."
            )

    def __str__(self):
        return self.full_name
