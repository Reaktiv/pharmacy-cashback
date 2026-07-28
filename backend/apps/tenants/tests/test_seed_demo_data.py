import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import Seller, UserProfile
from apps.broadcasts.models import Broadcast
from apps.ledger.models import Transaction
from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_seed_demo_data_creates_a_full_demo_tenant():
    call_command("seed_demo_data")

    tenant = Tenant.objects.get(slug="demo-pharmacy")
    assert str(tenant.cashback_rate) == "5.00"

    for username, role in [
        ("demo_superadmin", UserProfile.Role.SUPERADMIN),
        ("demo_tenantadmin", UserProfile.Role.TENANT_ADMIN),
        ("demo_branchmgr", UserProfile.Role.BRANCH_MANAGER),
        ("demo_seller", UserProfile.Role.SELLER),
    ]:
        user = User.objects.get(username=username)
        assert user.check_password("demo-pass-1234")
        assert user.profile.role == role

    assert Seller.objects.all_tenants().filter(tenant=tenant).exists()
    assert Transaction.objects.all_tenants().filter(tenant=tenant).count() >= 2
    assert Broadcast.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_seed_demo_data_is_idempotent_without_reset():
    call_command("seed_demo_data")
    call_command("seed_demo_data")  # must not raise, must not duplicate

    assert Tenant.objects.filter(slug="demo-pharmacy").count() == 1


@pytest.mark.django_db
def test_seed_demo_data_reset_wipes_and_recreates():
    call_command("seed_demo_data")
    original_tenant_id = Tenant.objects.get(slug="demo-pharmacy").id

    call_command("seed_demo_data", "--reset")

    tenant = Tenant.objects.get(slug="demo-pharmacy")
    assert tenant.id != original_tenant_id  # genuinely recreated, not reused
    assert User.objects.filter(username="demo_seller").count() == 1
