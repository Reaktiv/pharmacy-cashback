import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Seller, UserProfile


@pytest.mark.django_db
def test_superadmin_profile_must_not_have_tenant_or_branch(make_user, make_tenant):
    tenant = make_tenant("t")
    user = make_user()
    # make_user() already gave `user` an UNASSIGNED profile via the
    # post_save signal — mutate it in place rather than constructing a
    # second UserProfile, which would collide on the OneToOneField.
    profile = user.profile
    profile.role = UserProfile.Role.SUPERADMIN
    profile.tenant = tenant
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_tenant_admin_requires_a_tenant(make_user, make_tenant):
    user = make_user()
    profile = user.profile
    profile.role = UserProfile.Role.TENANT_ADMIN
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_tenant_admin_must_not_be_scoped_to_a_single_branch(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    user = make_user()
    profile = user.profile
    profile.role = UserProfile.Role.TENANT_ADMIN
    profile.tenant = tenant
    profile.branch = branch
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_tenant_admin_with_only_a_tenant_is_valid(make_user, make_tenant):
    tenant = make_tenant("t")
    user = make_user()
    profile = user.profile
    profile.role = UserProfile.Role.TENANT_ADMIN
    profile.tenant = tenant
    profile.full_clean()  # must not raise


@pytest.mark.django_db
def test_branch_manager_branch_must_belong_to_the_same_tenant(make_user, make_tenant, make_branch):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_b = make_branch(tenant_b)
    user = make_user()

    profile = user.profile
    profile.role = UserProfile.Role.BRANCH_MANAGER
    profile.tenant = tenant_a
    profile.branch = branch_b
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_seller_tenant_branch_must_match_linked_profile(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    other_tenant = make_tenant("o")
    branch = make_branch(tenant)
    other_branch = make_branch(other_tenant, name="Other")

    user = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)

    # Seller is a TenantScopedModel: full_clean() runs a uniqueness check on
    # `user` through the tenant-filtered manager, so it needs a bound tenant
    # context — same as any real request would have via TenantMiddleware.
    # clean() alone is what actually exercises the tenant/branch consistency
    # rule under test here, so we call it directly.
    mismatched = Seller(
        tenant=other_tenant,
        branch=other_branch,
        user=user,
        phone="+998900000000",
        full_name="Seller One",
    )
    with pytest.raises(ValidationError):
        mismatched.clean()

    matching = Seller(
        tenant=tenant, branch=branch, user=user, phone="+998900000000", full_name="Seller One"
    )
    matching.clean()  # must not raise


@pytest.mark.django_db
def test_creating_a_user_auto_provisions_an_unassigned_profile(django_user_model):
    user = django_user_model.objects.create_user(username="fresh", password="pass1234")

    profile = user.profile
    assert profile.role == UserProfile.Role.UNASSIGNED
    assert profile.tenant_id is None
    assert profile.branch_id is None


@pytest.mark.django_db
def test_unassigned_profile_must_not_have_tenant_or_branch(make_user, make_tenant):
    tenant = make_tenant("t")
    user = make_user()

    profile = user.profile
    assert profile.role == UserProfile.Role.UNASSIGNED  # the default from make_user()
    profile.tenant = tenant
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_seller_role_requires_an_existing_seller_record(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    user = make_user()

    profile = user.profile
    profile.role = UserProfile.Role.SELLER
    profile.tenant = tenant
    profile.branch = branch
    with pytest.raises(ValidationError):
        profile.full_clean()

    Seller.objects.all_tenants().create(
        tenant=tenant, branch=branch, user=user, phone="+998900000000", full_name="Seller One"
    )
    profile.full_clean()  # now that the Seller row exists, it's allowed


@pytest.mark.django_db
def test_creating_a_seller_record_syncs_the_linked_profile(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    user = make_user()  # starts UNASSIGNED, no tenant/branch

    Seller.objects.all_tenants().create(
        tenant=tenant, branch=branch, user=user, phone="+998900000000", full_name="Seller One"
    )

    user.profile.refresh_from_db()
    assert user.profile.role == UserProfile.Role.SELLER
    assert user.profile.tenant_id == tenant.id
    assert user.profile.branch_id == branch.id
