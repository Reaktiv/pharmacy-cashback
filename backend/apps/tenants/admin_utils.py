"""Shared ModelAdmin mixin for tenant-scoped FK dropdowns (CLAUDE.md §4).

`get_queryset` overrides route each ModelAdmin's own changelist through
`.all_tenants()`, but Django admin builds FK dropdown fields (e.g. Seller's
`branch`, Transaction's `customer`) separately via `formfield_for_foreignkey`.
Passing our own `queryset=` kwarg isn't enough on its own: Django's
`ForeignKey.formfield()` unconditionally evaluates
`related_model._default_manager.using(...)` to build a throwaway default
*before* merging in our override, and for a TenantManager target that raises
TenantContextError immediately — superadmin requests aren't scoped to a
single tenant. `bypass_tenant_context()` lets that discarded default resolve
without raising; the real queryset actually shown to the admin is always the
explicit `.all_tenants()` call below.

Saving a form (POST) hits the same wall a second time: Model.full_clean()
runs validate_unique(), which queries the model's own default manager
(`Bot.objects`, TenantManager) directly — nowhere near
formfield_for_foreignkey, so that override alone doesn't cover it.
changeform_view() wraps the *entire* add/change request (GET render, POST
validate_unique, and save_model) in the same bypass. This is safe precisely
because Django admin is superadmin-only tooling (CLAUDE.md §7c/§3, gated by
Django's own is_staff/is_superuser check before this code ever runs) — the
same audience `.all_tenants()` is meant for everywhere else.
"""

from apps.tenants.context import bypass_tenant_context


class TenantScopedAdminMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related_manager = getattr(db_field.related_model, "objects", None)
        if related_manager is not None and hasattr(related_manager, "all_tenants"):
            kwargs["queryset"] = related_manager.all_tenants()
            with bypass_tenant_context():
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        with bypass_tenant_context():
            return super().changeform_view(request, object_id, form_url, extra_context)
