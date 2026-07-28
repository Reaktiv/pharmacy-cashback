from django.core.management.base import BaseCommand

from apps.bot.tasks import _register_webhook_sync
from apps.tenants.models import Bot


class Command(BaseCommand):
    help = "Registers the Telegram webhook for every active Bot row."

    def handle(self, *args, **options):
        bots = Bot.objects.all_tenants().filter(is_active=True)
        if not bots:
            self.stdout.write("No active bots to register.")
            return

        for bot_row in bots:
            _register_webhook_sync(bot_row)
            self.stdout.write(self.style.SUCCESS(f"Registered webhook for {bot_row.username}"))
