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
            user = User.objects.create_user(username=username, password=password)
            # tenant/branch match the Seller row created just below by
            # construction (same variables), satisfying Seller.clean()'s
            # profile-consistency check without needing to re-derive it.
            UserProfile.objects.create(
                user=user, role=UserProfile.Role.SELLER, tenant=tenant, branch=branch
            )
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
