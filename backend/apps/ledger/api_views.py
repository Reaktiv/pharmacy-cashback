from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserProfile
from apps.accounts.permissions import IsBranchManager, IsSuperadmin, IsTenantAdmin
from apps.audit.services import log_action
from apps.ledger.models import Transaction
from apps.ledger.reports import (
    get_branch_report,
    get_cross_tenant_dashboard,
    get_daily_earn_spend_report,
    get_seller_report,
)
from apps.ledger.serializers import ReversalRequestSerializer, TransactionSerializer
from apps.ledger.services import post_reversal
from apps.tenants.models import Tenant


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
            for row in get_cross_tenant_dashboard()
        ]
        return Response(data)


class BranchReportView(APIView):
    permission_classes = [IsTenantAdmin | IsSuperadmin]

    def get(self, request):
        tenant = _resolve_report_tenant(request)
        data = [
            {
                "branch_id": row["branch"].id if row["branch"] else None,
                "branch_name": row["branch"].name if row["branch"] else "unknown",
                "total_earned": row["total_earned"],
                "total_spent": row["total_spent"],
                "outstanding": row["outstanding"],
            }
            for row in get_branch_report(tenant=tenant)
        ]
        return Response(data)


class SellerReportView(APIView):
    permission_classes = [IsTenantAdmin | IsBranchManager | IsSuperadmin]

    def get(self, request):
        profile = request.user.profile
        rows = get_seller_report(tenant=_resolve_report_tenant(request))
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


class DailyEarnSpendReportView(APIView):
    permission_classes = [IsTenantAdmin | IsSuperadmin]

    def get(self, request):
        tenant = _resolve_report_tenant(request)
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30
        rows = get_daily_earn_spend_report(tenant=tenant, days=days)
        return Response(rows)
