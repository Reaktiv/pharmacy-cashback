import pytest

from apps.audit.models import AuditLog
from apps.audit.services import log_action


@pytest.mark.django_db
def test_log_action_creates_an_entry(make_tenant, make_user):
    tenant = make_tenant("t")
    actor = make_user()

    entry = log_action(
        tenant=tenant,
        actor=actor,
        action="tenant_created",
        target_type="Tenant",
        target_id=tenant.id,
        metadata={"name": tenant.name},
    )

    assert entry.pk is not None
    assert entry.tenant_id == tenant.id
    assert entry.actor_id == actor.id
    assert entry.target_id == str(tenant.id)
    assert entry.metadata == {"name": tenant.name}


@pytest.mark.django_db
def test_audit_log_cannot_be_edited(make_tenant, make_user):
    tenant = make_tenant("t")
    entry = log_action(
        tenant=tenant,
        actor=make_user(),
        action="tenant_created",
        target_type="Tenant",
        target_id=tenant.id,
    )

    entry.action = "tampered"
    with pytest.raises(RuntimeError):
        entry.save()


@pytest.mark.django_db
def test_audit_log_cannot_be_deleted(make_tenant, make_user):
    tenant = make_tenant("t")
    entry = log_action(
        tenant=tenant,
        actor=make_user(),
        action="tenant_created",
        target_type="Tenant",
        target_id=tenant.id,
    )

    with pytest.raises(RuntimeError):
        entry.delete()


@pytest.mark.django_db
def test_log_action_allows_null_tenant_for_global_actions(make_user):
    entry = log_action(
        tenant=None,
        actor=make_user(),
        action="something_global",
        target_type="GlobalSettings",
        target_id=1,
    )
    assert entry.tenant is None


@pytest.mark.django_db
def test_audit_log_admin_is_read_only():
    from apps.audit.admin import AuditLogAdmin

    admin_instance = AuditLogAdmin(AuditLog, None)
    assert admin_instance.has_add_permission(None) is False
    assert admin_instance.has_change_permission(None) is False
    assert admin_instance.has_delete_permission(None) is False
