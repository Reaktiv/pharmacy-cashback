"""Deactivated-tenant access gate.

When a superadmin flips Tenant.is_active off, every login tied to that
tenant — its tenant admins, branch managers and sellers — is refused, at
both the login endpoints and on every authenticated request (existing JWT
sessions included). Superadmins have no `profile.tenant`, so they are never
affected.

This is enforced at read time rather than by cascading is_active onto the
User rows: reactivating the tenant then restores access immediately, with
no bookkeeping about which users were already individually deactivated.
"""

TENANT_INACTIVE_MESSAGE = "Kirish huquqingiz yo'q — dorixona faolsizlantirilgan."


def tenant_is_blocked(profile) -> bool:
    """True when this UserProfile belongs to a deactivated tenant."""
    tenant = getattr(profile, "tenant", None)
    return tenant is not None and not tenant.is_active
