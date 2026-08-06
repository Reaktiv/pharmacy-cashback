from django.contrib import admin

from apps.broadcasts.models import Broadcast, BroadcastDeliveryLog, BroadcastMedia
from apps.tenants.admin_utils import TenantScopedAdminMixin


@admin.register(Broadcast)
class BroadcastAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "tenant",
        "status",
        "media",
        "sent_count",
        "failed_count",
        "created_at",
    )
    list_filter = ("status",)

    def get_queryset(self, request):
        return Broadcast.objects.all_tenants()


@admin.register(BroadcastMedia)
class BroadcastMediaAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("original_filename", "tenant", "media_type", "size_bytes", "created_at")
    list_filter = ("media_type",)

    def get_queryset(self, request):
        return BroadcastMedia.objects.all_tenants()


@admin.register(BroadcastDeliveryLog)
class BroadcastDeliveryLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("broadcast", "customer", "status", "attempted_at")
    list_filter = ("status",)

    def get_queryset(self, request):
        return BroadcastDeliveryLog.objects.all_tenants()
