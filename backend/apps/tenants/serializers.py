from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Branch
from apps.bot.telegram_client import TelegramTokenValidationError, validate_bot_token
from apps.tenants.models import Bot, GlobalSettings, Tenant

# Same cap as the self-service avatar (apps/accounts/serializers.py) — a
# pharmacy logo, not a promotional image.
LOGO_MAX_BYTES = 5 * 1024 * 1024


class TenantSerializer(serializers.ModelSerializer):
    # Imported lazily inside the method (not at module level) to avoid a
    # cross-app import cycle: apps.broadcasts.models already imports from
    # apps.tenants.models.
    broadcasts_sent_this_month = serializers.SerializerMethodField()
    branches_count = serializers.SerializerMethodField()
    has_logo = serializers.SerializerMethodField()
    logo = serializers.FileField(write_only=True, required=False)
    remove_logo = serializers.BooleanField(write_only=True, required=False, default=False)
    # Explicit field + all_tenants() queryset for the same reason as
    # BotSerializer.tenant above: a superadmin request has no single
    # tenant bound, so Branch.objects (tenant-context-filtered) would
    # raise TenantContextError here. validate_receipt_branch below does
    # the real "does this branch belong to this tenant" check instead.
    receipt_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all_tenants(), required=False, allow_null=True
    )

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "is_active",
            "cashback_rate",
            "min_redeem_amount",
            "points_expiry_days",
            "default_daily_txn_limit",
            "broadcast_quota",
            "broadcasts_sent_this_month",
            "branch_limit",
            "branches_count",
            "has_logo",
            "logo",
            "remove_logo",
            "receipt_tin",
            "receipt_branch",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_has_logo(self, obj) -> bool:
        return bool(obj.logo)

    def validate_logo(self, uploaded_file):
        content_type = uploaded_file.content_type or ""
        if not content_type.startswith("image/"):
            raise serializers.ValidationError("Faqat rasm fayli yuklash mumkin.")
        if uploaded_file.size > LOGO_MAX_BYTES:
            raise serializers.ValidationError(
                f"Rasm hajmi {LOGO_MAX_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
        return uploaded_file

    def get_branches_count(self, obj) -> int:
        from apps.accounts.models import Branch

        return Branch.objects.all_tenants().filter(tenant=obj).count()

    def get_broadcasts_sent_this_month(self, obj) -> int:
        from apps.broadcasts.models import Broadcast

        # localtime(), not a raw now(): USE_TZ=True + TIME_ZONE=Asia/Tashkent
        # (CLAUDE.md §9) means a UTC-aware now() can read off the wrong
        # calendar month near midnight Tashkent time (UTC+5).
        now = timezone.localtime(timezone.now())
        return (
            Broadcast.objects.all_tenants()
            .filter(
                tenant=obj,
                platform_broadcast__isnull=True,
                status__in=[
                    Broadcast.Status.SENDING,
                    Broadcast.Status.SENT,
                    Broadcast.Status.FAILED,
                ],
                created_at__year=now.year,
                created_at__month=now.month,
            )
            .count()
        )

    def validate_receipt_branch(self, value):
        if value is not None:
            tenant_id = self.instance.id if self.instance is not None else None
            if value.tenant_id != tenant_id:
                raise serializers.ValidationError("Bu filial ushbu dorixonaga tegishli emas.")
        return value

    def validate_cashback_rate(self, value):
        cap = GlobalSettings.load().max_cashback_rate
        if value > cap:
            raise serializers.ValidationError(
                f"Cashback rate ({value}%) exceeds the global cap of {cap}%."
            )
        return value

    def validate(self, attrs):
        # CLAUDE.md §3: a tenant admin manages their own tenant's rate, but
        # slug/is_active/broadcast_quota/branch_limit are superadmin-only
        # levers (slug changes would break the tenant's webhook URL;
        # is_active is a platform-level kill switch; broadcast_quota and
        # branch_limit are paid-tier levers a tenant_admin must not be able
        # to raise for itself).
        request = self.context.get("request")
        profile = getattr(request.user, "profile", None) if request else None
        if profile is not None and profile.role != profile.Role.SUPERADMIN:
            for locked_field in ("slug", "is_active", "broadcast_quota", "branch_limit"):
                if locked_field in attrs and self.instance is not None:
                    if getattr(self.instance, locked_field) != attrs[locked_field]:
                        raise serializers.ValidationError(
                            {locked_field: "Only a superadmin can change this."}
                        )
        return attrs

    def create(self, validated_data):
        # Logo isn't set at creation time today (no tenant-creation form
        # offers it — see DashboardPage.tsx), same convention as
        # broadcast_quota/branch_limit; strip these so the default
        # ModelSerializer.create() doesn't choke passing them straight to
        # Tenant.objects.create().
        validated_data.pop("logo", None)
        validated_data.pop("remove_logo", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        logo = validated_data.pop("logo", None)
        remove_logo = validated_data.pop("remove_logo", False)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        update_fields = list(validated_data.keys())
        if remove_logo and instance.logo:
            instance.logo.delete(save=False)
            instance.logo = None
            update_fields.append("logo")
        elif logo is not None:
            instance.logo = logo
            update_fields.append("logo")
        instance.save(update_fields=update_fields or None)
        return instance


class GlobalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSettings
        fields = [
            "max_cashback_rate",
            "max_redeem_percent",
            "max_check_amount",
            "max_daily_redemptions_per_customer",
        ]


class BotSerializer(serializers.ModelSerializer):
    # tenant is a OneToOneField, so ModelSerializer would normally attach an
    # auto-generated UniqueValidator that queries Bot.objects (the
    # tenant-context-gated manager) to check "is this tenant already
    # used?" — but a superadmin request has no single tenant bound, so that
    # query would raise TenantContextError. validators=[] disables it in
    # favor of the explicit all_tenants() check in validate() below, same
    # escape-hatch pattern used everywhere else in this codebase.
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all(), validators=[])
    token = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Plaintext Telegram bot token — encrypted at rest, never returned.",
    )

    class Meta:
        model = Bot
        fields = ["id", "tenant", "username", "webhook_secret", "is_active", "token"]
        read_only_fields = ["id", "webhook_secret"]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("token"):
            raise serializers.ValidationError(
                {"token": "A token is required when creating a new bot."}
            )
        token = attrs.get("token")
        if token:
            # Applies identically whether this is a brand-new bot or a
            # token rotation on an existing one — CLAUDE.md-adjacent
            # settings-page requirement: never save a token Telegram
            # itself won't vouch for.
            try:
                validate_bot_token(token)
            except TelegramTokenValidationError as exc:
                raise serializers.ValidationError({"token": str(exc)}) from exc
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        if tenant is not None:
            existing = Bot.objects.all_tenants().filter(tenant=tenant)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"tenant": "This tenant already has a bot."}
                )
        return attrs

    def create(self, validated_data):
        token = validated_data.pop("token", None)
        instance = Bot(**validated_data)
        instance.set_token(token)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        token = validated_data.pop("token", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if token:
            instance.set_token(token)
        instance.save()
        return instance
