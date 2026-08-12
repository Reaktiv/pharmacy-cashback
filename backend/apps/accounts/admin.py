from django.contrib import admin

from apps.accounts.models import Branch, Seller, UserProfile
from apps.tenants.admin_utils import TenantScopedAdminMixin


@admin.register(UserProfile)
class UserProfileAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "full_name", "phone", "role", "tenant", "branch")
    list_filter = ("role",)


@admin.register(Branch)
class BranchAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "tenant", "is_active")

    def get_queryset(self, request):
        # Admin browses across tenants — the superadmin escape hatch
        # from CLAUDE.md §4.
        return Branch.objects.all_tenants()


@admin.register(Seller)
class SellerAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("full_name", "branch", "tenant", "is_active")

    def get_queryset(self, request):
        return Seller.objects.all_tenants()
