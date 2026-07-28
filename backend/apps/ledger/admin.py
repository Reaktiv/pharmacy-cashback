from django.contrib import admin

from apps.ledger.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
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
