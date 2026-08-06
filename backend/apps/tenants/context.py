"""Current-tenant storage (CLAUDE.md §4).

A contextvars.ContextVar rather than thread-local storage, so it stays
request-scoped correctly under async views too. TenantMiddleware sets it for
web requests; Phase 5's webhook view will set it for bot requests.
"""

import contextvars

_current_tenant: contextvars.ContextVar = contextvars.ContextVar(
    "current_tenant", default=None
)
_bypass_tenant_check: contextvars.ContextVar = contextvars.ContextVar(
    "bypass_tenant_check", default=False
)


def get_current_tenant():
    """Return the Tenant bound to this request/task, or None if unset."""
    return _current_tenant.get()


def set_current_tenant(tenant) -> contextvars.Token:
    return _current_tenant.set(tenant)


def reset_current_tenant(token: contextvars.Token) -> None:
    _current_tenant.reset(token)


def tenant_check_bypassed() -> bool:
    return _bypass_tenant_check.get()


class bypass_tenant_context:
    """Narrow, explicit escape hatch for provably superadmin-only code paths
    where TenantManager.get_queryset() would otherwise raise even though the
    caller is about to apply its own explicit filtering anyway.

    The motivating case: Django's ForeignKey.formfield() unconditionally
    builds `related_model._default_manager.using(...)` as a throwaway default
    *before* an explicitly-passed `queryset=` kwarg overrides it — so even
    though TenantScopedAdminMixin always supplies `.all_tenants()` as the
    real queryset, the discarded default still triggers TenantContextError.
    Within this block, TenantManager.get_queryset() returns an unfiltered
    queryset instead of raising. It does NOT relax any other call site — the
    same fail-closed default from CLAUDE.md §4 applies everywhere else."""

    def __enter__(self):
        self._token = _bypass_tenant_check.set(True)
        return self

    def __exit__(self, *exc_info):
        _bypass_tenant_check.reset(self._token)
