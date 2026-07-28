"""CLAUDE.md §5: AuditLog wired to rate changes, reversals, tenant/token
changes, and broadcasts — verified end to end through the real API."""

from decimal import Decimal

import pytest

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.ledger.services import post_earn_transaction


@pytest.mark.django_db
def test_tenant_creation_is_logged(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.post(
        "/api/tenants/",
        {"name": "New Co", "slug": "new-co", "cashback_rate": "5.00"},
        format="json",
    )

    assert response.status_code == 201
    entry = AuditLog.objects.get(action="tenant_created", target_id=str(response.data["id"]))
    assert entry.actor_id == superadmin.id
    assert entry.metadata["slug"] == "new-co"


@pytest.mark.django_db
def test_rate_change_is_logged_only_when_the_rate_actually_changes(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    # unrelated field, rate unchanged — must NOT log a rate_change
    client.patch(f"/api/tenants/{tenant.id}/", {"min_redeem_amount": "30000"}, format="json")
    assert not AuditLog.objects.filter(action="rate_change", target_id=str(tenant.id)).exists()

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"cashback_rate": "9.00"}, format="json"
    )

    assert response.status_code == 200
    entry = AuditLog.objects.get(action="rate_change", target_id=str(tenant.id))
    assert entry.actor_id == admin.id
    assert entry.metadata == {"old_rate": "5.00", "new_rate": "9.00"}


@pytest.mark.django_db
def test_bot_creation_and_token_rotation_are_logged_without_the_token(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    create_response = client.post(
        "/api/bots/",
        {"tenant": tenant.id, "username": "@bot", "token": "123456:SECRET-TOKEN-VALUE"},
        format="json",
    )
    bot_id = create_response.data["id"]

    created_entry = AuditLog.objects.get(action="bot_created", target_id=str(bot_id))
    assert "SECRET-TOKEN-VALUE" not in str(created_entry.metadata)
    assert "SECRET-TOKEN-VALUE" not in created_entry.action

    rotate_response = client.patch(
        f"/api/bots/{bot_id}/", {"token": "999999:ROTATED-SECRET"}, format="json"
    )
    assert rotate_response.status_code == 200

    rotated_entry = AuditLog.objects.get(action="bot_token_rotated", target_id=str(bot_id))
    assert "ROTATED-SECRET" not in str(rotated_entry.metadata)


@pytest.mark.django_db
def test_bot_update_without_token_does_not_log_a_rotation(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)
    bot_id = client.post(
        "/api/bots/",
        {"tenant": tenant.id, "username": "@bot", "token": "123456:SECRET"},
        format="json",
    ).data["id"]

    client.patch(f"/api/bots/{bot_id}/", {"is_active": False}, format="json")

    assert not AuditLog.objects.filter(action="bot_token_rotated", target_id=str(bot_id)).exists()


@pytest.mark.django_db
def test_reversal_writes_an_audit_log_entry(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    client = api_client_for(manager)

    response = client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    assert response.status_code == 201
    entry = AuditLog.objects.get(action="reversal", target_id=str(txn.pk))
    assert entry.actor_id == manager.id
    assert entry.tenant_id == tenant.id
    assert entry.metadata["reversal_id"] == response.data["id"]


@pytest.mark.django_db
def test_broadcast_create_and_send_are_both_logged(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    create_response = client.post(
        "/api/broadcasts/", {"title": "Sale!", "body": "20% off"}, format="json"
    )
    broadcast_id = create_response.data["id"]
    assert AuditLog.objects.filter(
        action="broadcast_created", target_id=str(broadcast_id)
    ).exists()

    client.post(f"/api/broadcasts/{broadcast_id}/send/")

    assert AuditLog.objects.filter(action="broadcast_sent", target_id=str(broadcast_id)).exists()
