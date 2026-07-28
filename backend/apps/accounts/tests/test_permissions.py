import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.accounts.models import UserProfile
from apps.accounts.permissions import IsBranchManager, IsSeller, IsSuperadmin, IsTenantAdmin

factory = APIRequestFactory()


def _view_requiring(permission_class):
    class ProtectedView(APIView):
        permission_classes = [permission_class]

        def get(self, request):
            return Response({"ok": True})

    return ProtectedView.as_view()


@pytest.mark.django_db
def test_tenant_admin_cannot_hit_superadmin_only_view(make_user, make_tenant):
    tenant = make_tenant("t")
    tenant_admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)

    view = _view_requiring(IsSuperadmin)
    request = factory.get("/protected/")
    force_authenticate(request, user=tenant_admin)
    response = view(request)

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_hit_superadmin_only_view(make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)

    view = _view_requiring(IsSuperadmin)
    request = factory.get("/protected/")
    force_authenticate(request, user=superadmin)
    response = view(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_seller_cannot_hit_branch_manager_only_view(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)

    view = _view_requiring(IsBranchManager)
    request = factory.get("/protected/")
    force_authenticate(request, user=seller)
    response = view(request)

    assert response.status_code == 403


@pytest.mark.django_db
def test_seller_can_hit_seller_only_view(make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)

    view = _view_requiring(IsSeller)
    request = factory.get("/protected/")
    force_authenticate(request, user=seller)
    response = view(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected():
    view = _view_requiring(IsTenantAdmin)
    request = factory.get("/protected/")
    response = view(request)

    assert response.status_code in (401, 403)
