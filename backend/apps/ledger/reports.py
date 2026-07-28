"""Read-only aggregation for the admin panel (CLAUDE.md §7c). Distinct from
apps/ledger/services.py, which owns the write-path cashback math — see
CLAUDE.md §9's project layout ("services.py (ALL cashback math), reports").

Every function here does its summing in the database (single aggregate
queries), never by looping over individual customers/transactions in
Python — same principle as get_balance in services.py. The one exception is
looping over *tenants* or *branches* (a handful of rows, not millions) to
build one report row each; that's normal admin-reporting shape, not the
per-customer balance computation the "never loop" rule is about.
"""

from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.models import Branch, Seller
from apps.customers.models import Customer
from apps.ledger.models import Transaction
from apps.tenants.models import Bot, Tenant


def get_total_liability(*, tenant: Tenant | None = None) -> Decimal:
    """CLAUDE.md §7c: total outstanding liability = sum of every
    customer's balance, which (addition being associative) is exactly
    SUM(earned) - SUM(spent) over the relevant transactions in one query —
    same identity get_balance relies on for a single customer.
    """
    qs = Transaction.objects.all_tenants()
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    aggregates = qs.aggregate(earned=Sum("cashback_earned"), spent=Sum("cashback_spent"))
    earned = aggregates["earned"] or Decimal("0")
    spent = aggregates["spent"] or Decimal("0")
    return earned - spent


def get_cross_tenant_dashboard() -> list[dict]:
    """CLAUDE.md §7c superadmin dashboard: one row per tenant —
    Bot | Tenant | Customers | Active(30d) | Today's txns | Total liability | Status.
    """
    today = timezone.localdate()
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)

    rows = []
    for tenant in Tenant.objects.all().order_by("name"):
        bot = Bot.objects.all_tenants().filter(tenant=tenant).first()
        customers_qs = Customer.objects.all_tenants().filter(tenant=tenant)
        rows.append(
            {
                "tenant": tenant,
                "bot": bot,
                "customers": customers_qs.count(),
                "active_30d": customers_qs.filter(
                    transactions__created_at__gte=thirty_days_ago
                )
                .distinct()
                .count(),
                "today_txns": Transaction.objects.all_tenants()
                .filter(tenant=tenant, created_at__date=today)
                .count(),
                "total_liability": get_total_liability(tenant=tenant),
                "status": "active" if tenant.is_active and bot and bot.is_active else "inactive",
            }
        )
    return rows


def get_branch_report(*, tenant: Tenant) -> list[dict]:
    """CLAUDE.md §7c: per-branch earned/spent/outstanding."""
    rows = (
        Transaction.objects.all_tenants()
        .filter(tenant=tenant)
        .values("branch_id")
        .annotate(total_earned=Sum("cashback_earned"), total_spent=Sum("cashback_spent"))
        .order_by("branch_id")
    )
    branches_by_id = {
        b.pk: b for b in Branch.objects.all_tenants().filter(pk__in=[r["branch_id"] for r in rows])
    }
    result = []
    for row in rows:
        earned = row["total_earned"] or Decimal("0")
        spent = row["total_spent"] or Decimal("0")
        result.append(
            {
                "branch": branches_by_id.get(row["branch_id"]),
                "total_earned": earned,
                "total_spent": spent,
                "outstanding": earned - spent,
            }
        )
    return result


def get_seller_report(*, tenant: Tenant, date_from=None, date_to=None) -> list[dict]:
    """CLAUDE.md §7c: per-seller transaction count & average check (fraud
    signal). Defaults to all-time; pass date_from/date_to (dates) to scope
    it to a range.
    """
    qs = Transaction.objects.all_tenants().filter(tenant=tenant, seller__isnull=False)
    if date_from is not None:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__date__lte=date_to)

    rows = (
        qs.values("seller_id")
        .annotate(
            txn_count=Count("id"),
            avg_check=Avg("check_amount"),
            flagged_count=Count("id", filter=Q(flagged=True)),
        )
        .order_by("seller_id")
    )
    sellers_by_id = {
        s.pk: s for s in Seller.objects.all_tenants().filter(pk__in=[r["seller_id"] for r in rows])
    }
    return [
        {
            "seller": sellers_by_id.get(row["seller_id"]),
            "txn_count": row["txn_count"],
            "avg_check": row["avg_check"] or Decimal("0"),
            "flagged_count": row["flagged_count"],
        }
        for row in rows
    ]


def get_daily_earn_spend_report(*, tenant: Tenant, days: int = 30) -> list[dict]:
    """CLAUDE.md §7c: daily earn/spend totals over the last `days` days."""
    since = timezone.localdate() - timezone.timedelta(days=days - 1)
    rows = (
        Transaction.objects.all_tenants()
        .filter(tenant=tenant, created_at__date__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total_earned=Sum("cashback_earned"), total_spent=Sum("cashback_spent"))
        .order_by("day")
    )
    return [
        {
            "day": row["day"],
            "total_earned": row["total_earned"] or Decimal("0"),
            "total_spent": row["total_spent"] or Decimal("0"),
        }
        for row in rows
    ]
