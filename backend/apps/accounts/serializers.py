from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Branch, Seller, UserProfile


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
