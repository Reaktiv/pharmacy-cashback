from django.contrib import admin

from apps.customers.models import OTP, Customer, PendingCashback
from apps.tenants.admin_utils import TenantScopedAdminMixin


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("phone", "full_name", "tenant", "is_active")

    def get_queryset(self, request):
        return Customer.objects.all_tenants()


@admin.register(PendingCashback)
class PendingCashbackAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("phone", "amount", "tenant", "claimed", "expires_at")

    def get_queryset(self, request):
        return PendingCashback.objects.all_tenants()


@admin.register(OTP)
class OTPAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("customer", "code", "amount_requested", "used", "expires_at")

    def get_queryset(self, request):
        return OTP.objects.all_tenants()
