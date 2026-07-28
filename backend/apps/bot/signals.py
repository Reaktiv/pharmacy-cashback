"""IMPLEMENTATION_PLAN.md Phase 5: adding a Bot row auto-registers its
webhook, no redeploy."""

from django.db import transaction as db_transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tenants.models import Bot


@receiver(post_save, sender=Bot)
def auto_register_webhook(sender, instance, **kwargs):
    from apps.bot.tasks import register_webhook

    db_transaction.on_commit(lambda: register_webhook.delay(instance.pk))
