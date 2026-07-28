from rest_framework import serializers

from apps.tenants.models import Bot, GlobalSettings, Tenant


class TenantSerializer(serializers.ModelSerializer):
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
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_cashback_rate(self, value):
        cap = GlobalSettings.load().max_cashback_rate
        if value > cap:
            raise serializers.ValidationError(
                f"Cashback rate ({value}%) exceeds the global cap of {cap}%."
            )
        return value

    def validate(self, attrs):
        # CLAUDE.md §3: a tenant admin manages their own tenant's rate, but
        # slug/is_active are superadmin-only levers (slug changes would
        # break the tenant's webhook URL; is_active is a platform-level
        # kill switch).
        request = self.context.get("request")
        profile = getattr(request.user, "profile", None) if request else None
        if profile is not None and profile.role != profile.Role.SUPERADMIN:
            for locked_field in ("slug", "is_active"):
                if locked_field in attrs and self.instance is not None:
                    if getattr(self.instance, locked_field) != attrs[locked_field]:
                        raise serializers.ValidationError(
                            {locked_field: "Only a superadmin can change this."}
                        )
        return attrs


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
