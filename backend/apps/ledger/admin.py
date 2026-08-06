from django.contrib import admin

from apps.ledger.models import Transaction
from apps.tenants.admin_utils import TenantScopedAdminMixin


@admin.register(Transaction)
class TransactionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "customer",
        "type",
        "status",
        "check_amount",
        "cashback_earned",
        "cashback_spent",
        "flagged",
        "created_at",
    )
    list_filter = ("type", "status", "flagged")

    def get_queryset(self, request):
        return Transaction.objects.all_tenants()
