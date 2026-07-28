"""Celery periodic tasks for ledger-level jobs (CLAUDE.md §8)."""

import logging

from celery import shared_task

from apps.accounts.models import Branch
from apps.ledger.services import get_daily_seller_summary

logger = logging.getLogger(__name__)


@shared_task
def send_daily_seller_summaries() -> None:
    """CLAUDE.md §8: daily per-seller summary "to the branch manager".

    No delivery channel to branch managers exists yet — they don't have bot
    access (the customer bot must never expose seller/manager actions, per
    §7a), and the manager-facing web panel is Phase 7. For now this
    computes and logs the summary per branch/seller so it's at least
    produced and inspectable; wiring real delivery (email, in-app, etc.) is
    future work once a channel exists.
    """
    for branch in Branch.objects.all_tenants().filter(is_active=True):
        for row in get_daily_seller_summary(branch=branch):
            seller = row["seller"]
            logger.info(
                "Daily seller summary | branch=%s seller=%s txns=%d earned=%s spent=%s "
                "avg_check=%s",
                branch.name,
                seller.full_name if seller else "unknown",
                row["txn_count"],
                row["total_earned"],
                row["total_spent"],
                row["avg_check"],
            )
