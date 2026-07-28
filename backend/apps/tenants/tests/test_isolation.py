"""The mandatory tenant-isolation test (CLAUDE.md §4).

CLAUDE.md names this test after real business models (Customer, Transaction,
Branch, Seller), but those don't exist until Phases 2-3. Per
IMPLEMENTATION_PLAN.md Phase 1, we prove the TenantScopedModel/TenantManager
mechanism itself here with two throwaway dummy models — every future
tenant-scoped model inherits the exact same behavior, so this is the real
security boundary under test. A second, model-specific version of this test
should be added once Customer/Transaction/Branch/Seller exist.
"""

from decimal import Decimal

from django.apps import apps as django_apps
from django.db import connection, models
from django.test import TestCase
from django.test.utils import isolate_apps

from apps.tenants.context import reset_current_tenant, set_current_tenant
from apps.tenants.models import Tenant, TenantContextError, TenantScopedModel


@isolate_apps("apps.tenants")
class TenantIsolationTests(TestCase):
    """A query as Tenant A must return zero rows belonging to Tenant B, and a
    query with no tenant bound in context must never leak rows either."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class DummyScopedRecord(TenantScopedModel):
            name = models.CharField(max_length=50)

            class Meta:
                app_label = "tenants"

        cls.DummyScopedRecord = DummyScopedRecord

        with connection.schema_editor() as editor:
            editor.create_model(DummyScopedRecord)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.DummyScopedRecord)
        super().tearDownClass()
        # isolate_apps restores the app registry but doesn't reliably clear
        # the *real* Tenant model's cached reverse-relation graph — since
        # DummyScopedRecord's tenant FK points at the real Tenant class,
        # Tenant._meta can keep a stale reference to the now-dropped table,
        # breaking any later test that cascades a delete through Tenant
        # (Django's deletion collector walks _meta.get_fields()). Both
        # calls are needed: clear_cache() covers the apps registry, but
        # Tenant._meta caches its own field/relation graph independently.
        # Belt and suspenders: if isolate_apps left any stale reference to
        # DummyScopedRecord in the *global* registry's model dict (rather
        # than its own isolated one), purge it directly — that's the
        # authoritative source Django rescans when rebuilding caches, so
        # clear_cache() alone can't fix a leak at this level.
        app_models = django_apps.all_models.get("tenants", {})
        app_models.pop("dummyscopedrecord", None)
        django_apps.clear_cache()
        Tenant._meta._expire_cache()

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A", slug="tenant-a", cashback_rate=Decimal("3.00")
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B", slug="tenant-b", cashback_rate=Decimal("3.00")
        )
        self.DummyScopedRecord.objects.all_tenants().create(
            tenant=self.tenant_a, name="tenant-a-secret"
        )
        self.DummyScopedRecord.objects.all_tenants().create(
            tenant=self.tenant_b, name="tenant-b-secret"
        )

    def test_tenant_a_admin_cannot_read_tenant_b_data(self):
        token = set_current_tenant(self.tenant_a)
        try:
            visible = list(self.DummyScopedRecord.objects.all())
        finally:
            reset_current_tenant(token)

        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].tenant_id, self.tenant_a.id)
        self.assertTrue(all(row.tenant_id != self.tenant_b.id for row in visible))

    def test_tenant_b_admin_cannot_read_tenant_a_data(self):
        token = set_current_tenant(self.tenant_b)
        try:
            visible = list(self.DummyScopedRecord.objects.all())
        finally:
            reset_current_tenant(token)

        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].tenant_id, self.tenant_b.id)

    def test_query_without_tenant_context_fails_closed_not_open(self):
        # No tenant bound at all — must never silently return every tenant's
        # rows. It's allowed to raise or return empty; it must never leak.
        with self.assertRaises(TenantContextError):
            list(self.DummyScopedRecord.objects.all())

    def test_all_tenants_escape_hatch_is_explicit_and_unfiltered(self):
        token = set_current_tenant(self.tenant_a)
        try:
            everyone = list(self.DummyScopedRecord.objects.all_tenants())
        finally:
            reset_current_tenant(token)

        self.assertEqual(len(everyone), 2)
