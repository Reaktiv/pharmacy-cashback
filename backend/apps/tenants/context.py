"""Current-tenant storage (CLAUDE.md §4).

A contextvars.ContextVar rather than thread-local storage, so it stays
request-scoped correctly under async views too. TenantMiddleware sets it for
web requests; Phase 5's webhook view will set it for bot requests.
"""

import contextvars

_current_tenant: contextvars.ContextVar = contextvars.ContextVar(
    "current_tenant", default=None
)


def get_current_tenant():
    """Return the Tenant bound to this request/task, or None if unset."""
    return _current_tenant.get()


def set_current_tenant(tenant) -> contextvars.Token:
    return _current_tenant.set(tenant)


def reset_current_tenant(token: contextvars.Token) -> None:
    _current_tenant.reset(token)
