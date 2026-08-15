from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Branch, Seller, UserProfile
from apps.tenants.models import GlobalSettings, Tenant

# Self-service profile picture — deliberately smaller than broadcast media's
# 10MB image cap (apps.broadcasts.serializers.MAX_IMAGE_BYTES): this is a
# small avatar, not a promotional image.
AVATAR_MAX_BYTES = 5 * 1024 * 1024


class TenantAwareTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Embeds role/tenant_id/branch_id as informational JWT claims.

    These claims are convenience for the frontend (e.g. to render "you're a
    seller for Branch X" without an extra round trip) — they are NOT used
    server-side for authorization. Every request re-derives tenant/role from
    the database via TenantMiddleware and UserProfile, so a stale token
    issued before a role/tenant change can't grant stale access.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        profile = getattr(user, "profile", None)
        token["role"] = profile.role if profile else None
        token["tenant_id"] = profile.tenant_id if profile else None
        token["branch_id"] = profile.branch_id if profile else None
        return token


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "is_active"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # Same shape as Tenant.broadcast_quota (apps/broadcasts/api_views.py
        # _quota_exceeded): superadmin sets a per-tenant cap on total branch
        # count, null = unlimited. Only checked on create — editing an
        # existing branch never adds to the count.
        if self.instance is None:
            tenant = self.context["request"].user.profile.tenant
            limit = tenant.branch_limit
            if limit is not None and Branch.objects.all().count() >= limit:
                raise serializers.ValidationError(
                    {"detail": f"Filiallar soni limiti tugagan (limit: {limit})."}
                )
        return attrs


class SellerSerializer(serializers.ModelSerializer):
    """Creating a Seller also provisions the login it needs (CLAUDE.md §5:
    "user (FK to Django User — sellers log into the web app)") — username/
    password are write-only inputs, not model fields."""

    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )

    class Meta:
        model = Seller
        fields = [
            "id",
            "branch",
            "phone",
            "full_name",
            "is_active",
            "daily_txn_limit",
            "username",
            "password",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("username") or not attrs.get("password"):
                raise serializers.ValidationError(
                    "username and password are required when creating a seller."
                )

        profile = self.context["request"].user.profile
        if profile.role == UserProfile.Role.BRANCH_MANAGER:
            branch = attrs.get("branch") or getattr(self.instance, "branch", None)
            if branch is not None and branch.pk != profile.branch_id:
                raise serializers.ValidationError(
                    {"branch": "You can only manage sellers in your own branch."}
                )
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        tenant = self.context["request"].user.profile.tenant
        branch = validated_data["branch"]
        if branch.tenant_id != tenant.id:
            raise serializers.ValidationError({"branch": "Branch must belong to your tenant."})

        with db_transaction.atomic():
            # User.objects.create_user() triggers a signal that gives `user`
            # a bare UNASSIGNED profile; creating the Seller row just below
            # triggers another signal that flips it to role=SELLER with this
            # tenant/branch (apps.accounts.signals).
            user = User.objects.create_user(username=username, password=password)
            seller = Seller.objects.all_tenants().create(
                tenant=tenant, user=user, **validated_data
            )
        return seller

    def update(self, instance, validated_data):
        validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if password:
            instance.user.set_password(password)
            instance.user.save(update_fields=["password"])
        return instance


class BranchManagerSerializer(serializers.Serializer):
    """Creates/manages a branch manager: a User + UserProfile(role=
    BRANCH_MANAGER) pair scoped to one branch within the tenant admin's own
    tenant (CLAUDE.md §3: tenant admin manages branch managers; only the
    branch manager themselves manages sellers — see SellerSerializer).

    There's no separate BranchManager model (CLAUDE.md §5) — UserProfile is
    the whole record, so this is a plain Serializer rather than a
    ModelSerializer.
    """

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    # `queryset=Branch.objects` (the manager, not `.all()`): DRF only calls
    # `.all()` on it lazily at validation time, when a request's tenant
    # context is actually bound — evaluating it eagerly here at class
    # definition time would hit TenantManager with no tenant bound yet.
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", required=False)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["username"] = instance.user.username
        return data

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("username") or not attrs.get("password"):
                raise serializers.ValidationError(
                    "username and password are required when creating a branch manager."
                )
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        tenant = self.context["request"].user.profile.tenant
        branch = validated_data["branch"]
        if branch.tenant_id != tenant.id:
            raise serializers.ValidationError({"branch": "Branch must belong to your tenant."})

        with db_transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": UserProfile.Role.BRANCH_MANAGER,
                    "tenant": tenant,
                    "branch": branch,
                },
            )
        return profile

    def update(self, instance, validated_data):
        validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        is_active = validated_data.pop("user", {}).get("is_active")
        branch = validated_data.get("branch")
        if branch is not None:
            tenant = self.context["request"].user.profile.tenant
            if branch.tenant_id != tenant.id:
                raise serializers.ValidationError({"branch": "Branch must belong to your tenant."})
            instance.branch = branch
            instance.save(update_fields=["branch"])
        if password:
            instance.user.set_password(password)
            instance.user.save(update_fields=["password"])
        if is_active is not None:
            instance.user.is_active = is_active
            instance.user.save(update_fields=["is_active"])
        return instance


class TenantAdminSerializer(serializers.Serializer):
    """Creates/manages a tenant admin login: a User + UserProfile(role=
    TENANT_ADMIN) pair scoped to one tenant (CLAUDE.md §3/§7c: the
    superadmin is the one who creates tenants, so they're also the one who
    provisions the login able to administer a freshly created tenant).

    Same no-separate-model shape as BranchManagerSerializer above — there is
    no dedicated TenantAdmin model, UserProfile is the whole record.
    """

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", required=False)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["username"] = instance.user.username
        return data

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("username") or not attrs.get("password"):
                raise serializers.ValidationError(
                    "username and password are required when creating a tenant admin."
                )
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        tenant = validated_data["tenant"]

        with db_transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": UserProfile.Role.TENANT_ADMIN,
                    "tenant": tenant,
                    "branch": None,
                },
            )
        return profile

    def update(self, instance, validated_data):
        validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        is_active = validated_data.pop("user", {}).get("is_active")
        tenant = validated_data.get("tenant")
        if tenant is not None:
            instance.tenant = tenant
            instance.save(update_fields=["tenant"])
        if password:
            instance.user.set_password(password)
            instance.user.save(update_fields=["password"])
        if is_active is not None:
            instance.user.is_active = is_active
            instance.user.save(update_fields=["is_active"])
        return instance


class MeSerializer(serializers.ModelSerializer):
    """Self-service `GET/PATCH /api/me/` for every internal role (superadmin,
    tenant admin, branch manager, seller) — an editable layer on top of
    whichever login the user already has, not a CLAUDE.md domain concern.
    Role/tenant/branch stay read-only here; that scoping is only ever
    changed by the admin flows above (TenantAdminSerializer etc.)."""

    username = serializers.CharField(source="user.username", read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    tenant_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    has_avatar = serializers.SerializerMethodField()
    avatar = serializers.FileField(write_only=True, required=False)
    remove_avatar = serializers.BooleanField(write_only=True, required=False, default=False)
    tenant_has_logo = serializers.SerializerMethodField()
    # Superadmin-only product-wide branding (CLAUDE.md §7c: every
    # tenant-scoped role sees their own Tenant.name/logo instead, via
    # tenant_name/tenant_has_logo above — this is the "Pharmacy Cashback"
    # brand itself). platform_name is deliberately a SerializerMethodField
    # (read) with its write side handled from self.initial_data in update()
    # below — it isn't a real UserProfile attribute, so it can't be a plain
    # model-bound field the way full_name/phone are.
    platform_name = serializers.SerializerMethodField()
    platform_has_logo = serializers.SerializerMethodField()
    platform_logo = serializers.FileField(write_only=True, required=False)
    remove_platform_logo = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = UserProfile
        fields = [
            "username",
            "role",
            "role_display",
            "tenant_name",
            "branch_name",
            "full_name",
            "phone",
            "language",
            "has_avatar",
            "avatar",
            "remove_avatar",
            "tenant_has_logo",
            "platform_name",
            "platform_has_logo",
            "platform_logo",
            "remove_platform_logo",
        ]
        read_only_fields = [
            "role",
            "role_display",
            "tenant_name",
            "branch_name",
            "has_avatar",
            "tenant_has_logo",
            "platform_has_logo",
        ]

    def get_tenant_name(self, obj) -> str | None:
        return obj.tenant.name if obj.tenant_id else None

    def get_branch_name(self, obj) -> str | None:
        return obj.branch.name if obj.branch_id else None

    def get_has_avatar(self, obj) -> bool:
        return bool(obj.avatar)

    def get_tenant_has_logo(self, obj) -> bool:
        return bool(obj.tenant.logo) if obj.tenant_id else False

    def get_platform_name(self, obj) -> str | None:
        if obj.role != UserProfile.Role.SUPERADMIN:
            return None
        return GlobalSettings.load().platform_name

    def get_platform_has_logo(self, obj) -> bool | None:
        if obj.role != UserProfile.Role.SUPERADMIN:
            return None
        return bool(GlobalSettings.load().platform_logo)

    def validate_avatar(self, uploaded_file):
        content_type = uploaded_file.content_type or ""
        if not content_type.startswith("image/"):
            raise serializers.ValidationError("Faqat rasm fayli yuklash mumkin.")
        if uploaded_file.size > AVATAR_MAX_BYTES:
            raise serializers.ValidationError(
                f"Rasm hajmi {AVATAR_MAX_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
        return uploaded_file

    def validate_platform_logo(self, uploaded_file):
        content_type = uploaded_file.content_type or ""
        if not content_type.startswith("image/"):
            raise serializers.ValidationError("Faqat rasm fayli yuklash mumkin.")
        if uploaded_file.size > AVATAR_MAX_BYTES:
            raise serializers.ValidationError(
                f"Rasm hajmi {AVATAR_MAX_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
        return uploaded_file

    def update(self, instance, validated_data):
        avatar = validated_data.get("avatar", None)
        remove_avatar = validated_data.get("remove_avatar", False)
        instance.full_name = validated_data.get("full_name", instance.full_name)
        instance.phone = validated_data.get("phone", instance.phone)
        instance.language = validated_data.get("language", instance.language)
        update_fields = ["full_name", "phone", "language"]
        if remove_avatar and instance.avatar:
            instance.avatar.delete(save=False)
            instance.avatar = None
            update_fields.append("avatar")
        elif avatar is not None:
            instance.avatar = avatar
            update_fields.append("avatar")
        instance.save(update_fields=update_fields)

        # A seller's full_name/phone are authoritatively read from Seller
        # elsewhere (SellerSerializer, reports, the Sellers list) — push a
        # self-service edit back there too so those views don't go stale.
        seller = getattr(instance.user, "seller_profile", None)
        if seller is not None and (
            seller.full_name != instance.full_name or seller.phone != instance.phone
        ):
            seller.full_name = instance.full_name
            seller.phone = instance.phone
            seller.save(update_fields=["full_name", "phone"])

        if instance.role == UserProfile.Role.SUPERADMIN:
            gs = GlobalSettings.load()
            gs_update_fields = []
            new_platform_name = self.initial_data.get("platform_name")
            if isinstance(new_platform_name, str) and new_platform_name.strip():
                new_platform_name = new_platform_name.strip()[:100]
                if new_platform_name != gs.platform_name:
                    gs.platform_name = new_platform_name
                    gs_update_fields.append("platform_name")
            platform_logo = validated_data.get("platform_logo")
            remove_platform_logo = validated_data.get("remove_platform_logo", False)
            if remove_platform_logo and gs.platform_logo:
                gs.platform_logo.delete(save=False)
                gs.platform_logo = None
                gs_update_fields.append("platform_logo")
            elif platform_logo is not None:
                gs.platform_logo = platform_logo
                gs_update_fields.append("platform_logo")
            if gs_update_fields:
                gs.save(update_fields=gs_update_fields)

        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """Self-service password change for `POST /api/me/change-password/` —
    every role (login itself is never editable here, only the password
    behind it). Django's own AUTH_PASSWORD_VALIDATORS run against
    new_password, same rules as everywhere else a password is set."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Joriy parol noto'g'ri.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
