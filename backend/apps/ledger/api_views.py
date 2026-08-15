from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Seller, UserProfile
from apps.accounts.permissions import IsBranchManager, IsSuperadmin, IsTenantAdmin
from apps.audit.services import log_action
from apps.ledger.models import Transaction
from apps.ledger.reports import (
    DEFAULT_SELLER_TRANSACTIONS_PAGE_SIZE,
    get_branch_report,
    get_cross_tenant_dashboard,
    get_daily_earn_spend_report,
    get_seller_report,
    get_seller_transactions,
)
from apps.ledger.serializers import ReversalRequestSerializer, TransactionSerializer
from apps.ledger.services import post_reversal
from apps.tenants.models import Tenant

MAX_SELLER_TRANSACTIONS_LIMIT = 500

CROSS_TENANT_DASHBOARD_CACHE_KEY = "ledger:cross_tenant_dashboard"
CROSS_TENANT_DASHBOARD_CACHE_TTL = 60  # seconds; monitoring data, not a write-path check

BRANCH_REPORT_CACHE_TTL = 60  # seconds; same reasoning as CROSS_TENANT_DASHBOARD_CACHE_TTL

SELLER_REPORT_CACHE_TTL = 60  # seconds; same reasoning as CROSS_TENANT_DASHBOARD_CACHE_TTL

DAILY_REPORT_CACHE_TTL = 60  # seconds; same reasoning as CROSS_TENANT_DASHBOARD_CACHE_TTL


def _resolve_report_tenant(request):
    """Tenant admin/branch manager reports are always their own tenant. A
    superadmin has no single tenant, so CLAUDE.md §7c's "clicking a row
    drills into that tenant" needs an explicit ?tenant_id= for these
    endpoints when called by a superadmin."""
    profile = request.user.profile
    if profile.role == UserProfile.Role.SUPERADMIN:
        tenant_id = request.query_params.get("tenant_id")
        if not tenant_id:
            raise ValidationError({"tenant_id": "Required for superadmin requests."})
        try:
            return Tenant.objects.get(pk=tenant_id)
        except (Tenant.DoesNotExist, ValueError) as exc:
            raise ValidationError({"tenant_id": "Tenant not found."}) from exc
    return profile.tenant


class ReversalView(APIView):
    """CLAUDE.md §3: "Branch Manager: ... issue reversals" — scoped to
    their own branch only."""

    permission_classes = [IsBranchManager]

    def post(self, request):
        serializer = ReversalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction_id = serializer.validated_data["transaction_id"]

        profile = request.user.profile
        txn = (
            Transaction.objects.all_tenants()
            .filter(pk=transaction_id, tenant_id=profile.tenant_id, branch_id=profile.branch_id)
            .first()
        )
        if txn is None:
            return Response({"detail": "Transaction not found in your branch."}, status=404)

        try:
            reversal = post_reversal(original_txn=txn, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        log_action(
            tenant=txn.tenant,
            actor=request.user,
            action="reversal",
            target_type="Transaction",
            target_id=txn.id,
            metadata={"reversal_id": reversal.id},
        )

        return Response(TransactionSerializer(reversal).data, status=201)


class CrossTenantDashboardView(APIView):
    """CLAUDE.md §7c superadmin dashboard."""

    permission_classes = [IsSuperadmin]

    def get(self, request):
        # No query params and superadmin-only means every caller gets the
        # exact same rows, so a single global key is enough (same reasoning
        # as GlobalSettings.load() in apps/tenants/models.py). The TTL alone
        # is the invalidation strategy — tenant creation/status changes are
        # rare, manual admin actions with no financial consequence to a
        # cache lagging up to 60s, so there's no cache.delete() on write
        # here unlike GlobalSettings (whose cached values feed the earn/
        # redeem math directly).
        rows = cache.get(CROSS_TENANT_DASHBOARD_CACHE_KEY)
        if rows is None:
            rows = get_cross_tenant_dashboard()
            cache.set(CROSS_TENANT_DASHBOARD_CACHE_KEY, rows, CROSS_TENANT_DASHBOARD_CACHE_TTL)

        data = [
            {
                "tenant_id": row["tenant"].id,
                "tenant_name": row["tenant"].name,
                "bot_username": row["bot"].username if row["bot"] else None,
                "bot_active": row["bot"].is_active if row["bot"] else None,
                "customers": row["customers"],
                "active_30d": row["active_30d"],
                "today_txns": row["today_txns"],
                "total_liability": row["total_liability"],
                "status": row["status"],
            }
            for row in rows
        ]
        return Response(data)


class BranchReportView(APIView):
    permission_classes = [IsTenantAdmin | IsSuperadmin]

    def get(self, request):
        tenant = _resolve_report_tenant(request)

        # Unlike CrossTenantDashboardView's single global key, this result
        # is tenant-scoped (a superadmin can request any tenant via
        # ?tenant_id=), so the cache key must include tenant.id — a shared
        # key here would leak one tenant's branch figures into another
        # tenant's response. Keyed by tenant, not by the requesting user:
        # every caller allowed to see this tenant's report sees the same
        # rows, so they should share one cache entry rather than each
        # getting their own copy.
        cache_key = f"ledger:branch_report:{tenant.id}"
        rows = cache.get(cache_key)
        if rows is None:
            rows = get_branch_report(tenant=tenant)
            cache.set(cache_key, rows, BRANCH_REPORT_CACHE_TTL)

        data = [
            {
                "branch_id": row["branch"].id if row["branch"] else None,
                "branch_name": row["branch"].name if row["branch"] else "unknown",
                "total_earned": row["total_earned"],
                "total_spent": row["total_spent"],
                "outstanding": row["outstanding"],
            }
            for row in rows
        ]
        return Response(data)


class SellerReportView(APIView):
    permission_classes = [IsTenantAdmin | IsBranchManager | IsSuperadmin]

    def get(self, request):
        profile = request.user.profile
        tenant = _resolve_report_tenant(request)

        # Cache holds only the tenant-wide raw report — the same rows a
        # tenant_admin and every branch_manager in this tenant start from.
        # The branch_manager filter below runs on every request, after the
        # cache lookup, since it's a cheap in-memory list comprehension
        # (not a DB query) and its result depends on which branch_manager
        # is asking — caching post-filter would need a key per branch,
        # fragmenting one tenant's report into N cache entries for no
        # benefit (see BranchReportView's tenant-not-user reasoning above).
        cache_key = f"ledger:seller_report:{tenant.id}"
        rows = cache.get(cache_key)
        if rows is None:
            rows = get_seller_report(tenant=tenant)
            cache.set(cache_key, rows, SELLER_REPORT_CACHE_TTL)

        if profile.role == UserProfile.Role.BRANCH_MANAGER:
            rows = [
                row
                for row in rows
                if row["seller"] and row["seller"].branch_id == profile.branch_id
            ]
        data = [
            {
                "seller_id": row["seller"].id if row["seller"] else None,
                "seller_name": row["seller"].full_name if row["seller"] else "unknown",
                "txn_count": row["txn_count"],
                "avg_check": row["avg_check"],
                "flagged_count": row["flagged_count"],
            }
            for row in rows
        ]
        return Response(data)


class SellerTransactionsView(APIView):
    """Drill-down from the seller report row: full transaction history for
    one seller, newest first, scoped the same way as SellerReportView. A
    branch manager may only pull sellers from their own branch."""

    permission_classes = [IsTenantAdmin | IsBranchManager | IsSuperadmin]

    def get(self, request):
        seller_id = request.query_params.get("seller_id")
        if not seller_id:
            raise ValidationError({"seller_id": "Required."})

        tenant = _resolve_report_tenant(request)
        try:
            seller = Seller.objects.all_tenants().get(pk=seller_id, tenant=tenant)
        except (Seller.DoesNotExist, ValueError):
            return Response({"detail": "Seller not found."}, status=404)

        profile = request.user.profile
        if (
            profile.role == UserProfile.Role.BRANCH_MANAGER
            and seller.branch_id != profile.branch_id
        ):
            return Response({"detail": "Seller not found."}, status=404)

        try:
            limit = int(request.query_params.get("limit", DEFAULT_SELLER_TRANSACTIONS_PAGE_SIZE))
            offset = int(request.query_params.get("offset", 0))
        except ValueError as exc:
            raise ValidationError(
                {"limit": "Must be an integer.", "offset": "Must be an integer."}
            ) from exc
        if limit < 1 or limit > MAX_SELLER_TRANSACTIONS_LIMIT:
            raise ValidationError(
                {"limit": f"Must be between 1 and {MAX_SELLER_TRANSACTIONS_LIMIT}."}
            )
        if offset < 0:
            raise ValidationError({"offset": "Must be non-negative."})

        page = get_seller_transactions(
            tenant=tenant, seller_id=seller.id, limit=limit, offset=offset
        )
        return Response(
            {
                "results": [
                    {
                        "id": txn.id,
                        "created_at": txn.created_at,
                        "customer_phone": txn.customer.phone,
                        "check_amount": txn.check_amount,
                        "cash_paid": txn.cash_paid,
                        "cashback_earned": txn.cashback_earned,
                        "cashback_spent": txn.cashback_spent,
                        "no_cashback": txn.no_cashback,
                        "type": txn.type,
                        "status": txn.status,
                        "flagged": txn.flagged,
                    }
                    for txn in page.results
                ],
                "count": page.count,
                "totals": {
                    "check_amount": page.total_check_amount,
                    "cashback_earned": page.total_cashback_earned,
                    "cashback_spent": page.total_cashback_spent,
                },
            }
        )


class DailyEarnSpendReportView(APIView):
    permission_classes = [IsTenantAdmin | IsSuperadmin]

    def get(self, request):
        tenant = _resolve_report_tenant(request)
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30

        # Result depends on both tenant and days (ReportsPage.tsx uses 30,
        # TenantDetailPage.tsx uses 14 — see CLAUDE.md discussion for this
        # step), so both must be in the key or one page's request would
        # serve another page's window under a different tenant/days
        # combination. days isn't range-checked here (pre-existing, out of
        # this cache's scope) — an unusual value just produces its own
        # cache entry, no different from any other days value.
        cache_key = f"ledger:daily_report:{tenant.id}:{days}"
        rows = cache.get(cache_key)
        if rows is None:
            rows = get_daily_earn_spend_report(tenant=tenant, days=days)
            cache.set(cache_key, rows, DAILY_REPORT_CACHE_TTL)

        return Response(rows)
