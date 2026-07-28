from django.contrib import admin

from apps.broadcasts.models import Broadcast


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "status", "sent_count", "failed_count", "created_at")
    list_filter = ("status",)

    def get_queryset(self, request):
        return Broadcast.objects.all_tenants()
