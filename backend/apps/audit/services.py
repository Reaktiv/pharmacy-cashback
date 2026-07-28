"""CLAUDE.md §5: log rate changes, reversals, tenant/token changes, and
broadcasts here. Never pass a plaintext secret (e.g. a bot token) in
metadata — log that a change happened, not the value.
"""

from apps.audit.models import AuditLog


def log_action(
    *, tenant, actor, action: str, target_type: str, target_id, metadata=None
) -> AuditLog:
    return AuditLog.objects.create(
        tenant=tenant,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata or {},
    )
