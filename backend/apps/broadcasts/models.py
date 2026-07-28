from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel


class Broadcast(TenantScopedModel):
    """CLAUDE.md §5. Pulled forward from Phase 8 into Phase 7, since Phase
    7's own done-criterion ("tenant admin ... sends a broadcast") requires
    it — see apps.broadcasts.tasks for the throttled Celery send."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"

    title = models.CharField(max_length=255)
    body = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
