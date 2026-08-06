from django.urls import path

from apps.ledger.api_views import (
    BranchReportView,
    CrossTenantDashboardView,
    DailyEarnSpendReportView,
    ReversalView,
    SellerReportView,
    SellerTransactionsView,
)

urlpatterns = [
    path("reversals/", ReversalView.as_view(), name="reversal"),
    path("reports/cross-tenant/", CrossTenantDashboardView.as_view(), name="cross-tenant-report"),
    path("reports/branches/", BranchReportView.as_view(), name="branch-report"),
    path("reports/sellers/", SellerReportView.as_view(), name="seller-report"),
    path(
        "reports/seller-transactions/",
        SellerTransactionsView.as_view(),
        name="seller-transactions-report",
    ),
    path("reports/daily/", DailyEarnSpendReportView.as_view(), name="daily-report"),
]
