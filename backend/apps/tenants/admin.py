from django import forms
from django.contrib import admin

from apps.audit.services import log_action
from apps.bot.telegram_client import TelegramTokenValidationError, validate_bot_token
from apps.tenants.admin_utils import TenantScopedAdminMixin
from apps.tenants.models import Bot, GlobalSettings, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """CLAUDE.md §5: audit rate changes and tenant creation here too — the
    React panel isn't the only way a superadmin can touch these fields."""

    list_display = ("name", "slug", "cashback_rate", "branch_limit", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}

    def save_model(self, request, obj, form, change):
        old_rate = Tenant.objects.get(pk=obj.pk).cashback_rate if change else None
        super().save_model(request, obj, form, change)
        if not change:
            log_action(
                tenant=obj,
                actor=request.user,
                action="tenant_created",
                target_type="Tenant",
                target_id=obj.id,
                metadata={"name": obj.name, "slug": obj.slug},
            )
        elif old_rate is not None and obj.cashback_rate != old_rate:
            log_action(
                tenant=obj,
                actor=request.user,
                action="rate_change",
                target_type="Tenant",
                target_id=obj.id,
                metadata={"old_rate": str(old_rate), "new_rate": str(obj.cashback_rate)},
            )


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "max_cashback_rate",
        "max_redeem_percent",
        "max_check_amount",
        "max_daily_redemptions_per_customer",
    )

    def has_add_permission(self, request):
        # Singleton: only ever one row (see GlobalSettings.load()).
        return not GlobalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class BotAdminForm(forms.ModelForm):
    """token_encrypted is never editable directly — that would mean pasting
    an already-encrypted value into a plain text box. This form exposes a
    plaintext, write-only `token` field instead, encrypted via
    Bot.set_token() on save (CLAUDE.md §5: never store a plaintext token)."""

    token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=(
            "Paste the real Telegram bot token here — it will be encrypted at rest "
            "and never shown again. Leave blank when editing to keep the current token."
        ),
    )

    class Meta:
        model = Bot
        exclude = ["token_encrypted"]

    def clean_token(self):
        token = self.cleaned_data.get("token")
        if not token:
            return token
        # Same rule as the API path (apps/tenants/serializers.py::BotSerializer)
        # — kept in one place (apps/bot/telegram_client.py::validate_bot_token)
        # so admin and API can't drift on what counts as a valid token.
        try:
            validate_bot_token(token)
        except TelegramTokenValidationError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return token

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk is None and not cleaned.get("token"):
            raise forms.ValidationError("A token is required when creating a new bot.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        token = self.cleaned_data.get("token")
        if token:
            instance.set_token(token)
        if commit:
            instance.save()
        return instance


@admin.register(Bot)
class BotAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    form = BotAdminForm
    list_display = ("username", "tenant", "is_active")
    readonly_fields = ("webhook_secret",)

    def get_queryset(self, request):
        # Admin browses across tenants; this is exactly the superadmin
        # escape hatch described in CLAUDE.md §4.
        return Bot.objects.all_tenants()

    def save_model(self, request, obj, form, change):
        token_rotated = bool(form.cleaned_data.get("token"))
        super().save_model(request, obj, form, change)
        if not change:
            log_action(
                tenant=obj.tenant,
                actor=request.user,
                action="bot_created",
                target_type="Bot",
                target_id=obj.id,
                metadata={"username": obj.username},  # never the token itself
            )
        elif token_rotated:
            log_action(
                tenant=obj.tenant,
                actor=request.user,
                action="bot_token_rotated",
                target_type="Bot",
                target_id=obj.id,
                metadata={"username": obj.username},
            )
