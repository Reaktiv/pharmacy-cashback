"""IMPLEMENTATION_PLAN.md Phase 8: seed/demo data command. Formalizes the
manual click-test seeding used throughout development into a reusable,
idempotent command — safe to re-run; skips if the demo tenant already
exists unless --reset is passed.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from apps.accounts.models import Branch, Seller, UserProfile
from apps.audit.services import log_action
from apps.broadcasts.models import Broadcast
from apps.customers.models import Customer
from apps.ledger.services import post_earn_transaction, post_reversal
from apps.tenants.models import Bot, GlobalSettings, Tenant

DEMO_SLUG = "demo-pharmacy"
DEMO_PASSWORD = "demo-pass-1234"  # noqa: S105 - seed data only, never used in production


class Command(BaseCommand):
    help = "Seeds a demo tenant with realistic data for local exploration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the existing demo tenant (if any) and reseed from scratch.",
        )

    def handle(self, *args, **options):
        existing = Tenant.objects.filter(slug=DEMO_SLUG).first()
        if existing and not options["reset"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Demo tenant '{DEMO_SLUG}' already exists — pass --reset to reseed it."
                )
            )
            return
        if existing and options["reset"]:
            # PROTECT on Transaction/Branch/Customer means this only succeeds
            # once the ledger is empty; deleting demo-only rows here keeps
            # --reset usable without asking the user to clean up by hand.
            self._wipe_existing(existing)

        with db_transaction.atomic():
            self._seed()

        self.stdout.write(self.style.SUCCESS("Demo data seeded. Login credentials:"))
        for username, role in [
            ("demo_superadmin", "superadmin"),
            ("demo_tenantadmin", "tenant_admin"),
            ("demo_branchmgr", "branch_manager"),
            ("demo_seller", "seller (use the /seller/ web page, not the API)"),
        ]:
            self.stdout.write(f"  {username} / {DEMO_PASSWORD}  ({role})")

    def _wipe_existing(self, tenant: Tenant) -> None:
        from apps.ledger.models import Transaction

        # Broadcast.created_by and Transaction.customer/branch are all
        # PROTECT, so both must go before the users/tenant they reference.
        # Transaction.reverses is a self-referencing PROTECT too — a
        # reversal row protects the original it points at, so deleting the
        # whole queryset in one call fails; reversal rows must go first.
        Broadcast.objects.all_tenants().filter(tenant=tenant).delete()
        Transaction.objects.all_tenants().filter(tenant=tenant, reverses__isnull=False).delete()
        Transaction.objects.all_tenants().filter(tenant=tenant).delete()
        User.objects.filter(username__startswith="demo_").delete()
        tenant.delete()

    def _seed(self) -> None:
        GlobalSettings.load()

        superadmin, _ = User.objects.get_or_create(username="demo_superadmin")
        superadmin.set_password(DEMO_PASSWORD)
        superadmin.save()
        # update_or_create, not get_or_create: creating `superadmin` above
        # already triggered the post_save signal that gives it a bare
        # UNASSIGNED profile, so get_or_create would find that row and never
        # apply the SUPERADMIN role.
        UserProfile.objects.update_or_create(
            user=superadmin, defaults={"role": UserProfile.Role.SUPERADMIN}
        )

        tenant = Tenant.objects.create(
            name="Demo Pharmacy", slug=DEMO_SLUG, cashback_rate=Decimal("5.00")
        )
        log_action(
            tenant=tenant,
            actor=superadmin,
            action="tenant_created",
            target_type="Tenant",
            target_id=tenant.id,
            metadata={"name": tenant.name, "slug": tenant.slug},
        )

        bot = Bot.objects.all_tenants().create(tenant=tenant, username="@demo_pharmacy_bot")
        bot.set_token("000000:DEMO-TOKEN-NOT-A-REAL-BOT")
        bot.save()
        log_action(
            tenant=tenant,
            actor=superadmin,
            action="bot_created",
            target_type="Bot",
            target_id=bot.id,
            metadata={"username": bot.username},
        )

        tenant_admin = User.objects.create_user(username="demo_tenantadmin", password=DEMO_PASSWORD)
        UserProfile.objects.update_or_create(
            user=tenant_admin, defaults={"role": UserProfile.Role.TENANT_ADMIN, "tenant": tenant}
        )

        branch = Branch.objects.all_tenants().create(
            tenant=tenant, name="Main Branch", address="123 Amir Temur St"
        )

        branch_manager = User.objects.create_user(
            username="demo_branchmgr", password=DEMO_PASSWORD
        )
        UserProfile.objects.update_or_create(
            user=branch_manager,
            defaults={
                "role": UserProfile.Role.BRANCH_MANAGER,
                "tenant": tenant,
                "branch": branch,
            },
        )

        # No explicit UserProfile.objects.create() for the seller: creating
        # the Seller row below triggers apps.accounts.signals to flip its
        # profile to role=SELLER with this tenant/branch automatically.
        seller_user = User.objects.create_user(username="demo_seller", password=DEMO_PASSWORD)
        seller = Seller.objects.all_tenants().create(
            tenant=tenant,
            branch=branch,
            user=seller_user,
            phone="+998901112233",
            full_name="Demo Seller",
        )

        registered_customer = Customer.objects.all_tenants().create(
            tenant=tenant,
            phone="+998901234567",
            full_name="Aziz Karimov",
            telegram_id=100000001,
        )
        Customer.objects.all_tenants().create(
            tenant=tenant, phone="+998907654321", full_name="Malika Yusupova"
        )

        txn1 = post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=registered_customer,
            check_amount=Decimal("120000"),
            idempotency_key="seed-1",
        )
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=registered_customer,
            check_amount=Decimal("60000"),
            idempotency_key="seed-2",
        )
        reversal = post_reversal(original_txn=txn1, actor=tenant_admin)
        # Mirror what ReversalView does for a real reversal — this call
        # bypasses the API, so nothing would log it otherwise.
        log_action(
            tenant=tenant,
            actor=tenant_admin,
            action="reversal",
            target_type="Transaction",
            target_id=txn1.id,
            metadata={"reversal_id": reversal.id},
        )

        broadcast = Broadcast.objects.all_tenants().create(
            tenant=tenant,
            title="Welcome!",
            body="Thanks for being a loyal customer.",
            created_by=tenant_admin,
        )
        log_action(
            tenant=tenant,
            actor=tenant_admin,
            action="broadcast_created",
            target_type="Broadcast",
            target_id=broadcast.id,
            metadata={"title": broadcast.title},
        )
