from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """CLAUDE.md §5. Append-only — never edited or deleted.

    Deliberately NOT a TenantScopedModel: tenant is nullable for global
    actions (e.g. a superadmin creating a tenant, which doesn't belong to
    any tenant's own scope yet), and some entries are written from
    superadmin code paths with no single tenant bound to the ambient
    context — the same reasoning that keeps UserProfile off TenantManager.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", null=True, blank=True, on_delete=models.SET_NULL
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("AuditLog entries are append-only and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog entries are append-only and cannot be deleted.")

    def __str__(self):
        return f"{self.action} on {self.target_type}:{self.target_id}"
