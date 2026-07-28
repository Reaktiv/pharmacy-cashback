"""Role-based DRF permission classes (CLAUDE.md §3, IMPLEMENTATION_PLAN Phase 2).

Each checks an exact role match — no hierarchy (a superadmin does not
automatically pass IsTenantAdmin). Roles are distinct scopes, not a ladder.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import UserProfile


class HasRole(BasePermission):
    required_role: str = ""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        profile = getattr(user, "profile", None)
        return bool(profile and profile.role == self.required_role)


class IsSuperadmin(HasRole):
    required_role = UserProfile.Role.SUPERADMIN  # type: ignore[assignment]


class IsTenantAdmin(HasRole):
    required_role = UserProfile.Role.TENANT_ADMIN  # type: ignore[assignment]


class IsBranchManager(HasRole):
    required_role = UserProfile.Role.BRANCH_MANAGER  # type: ignore[assignment]


class IsSeller(HasRole):
    required_role = UserProfile.Role.SELLER  # type: ignore[assignment]
