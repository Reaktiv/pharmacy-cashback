from django.urls import reverse
from rest_framework import serializers

from apps.broadcasts.models import (
    Broadcast,
    BroadcastMedia,
    PlatformBroadcast,
    PlatformBroadcastMedia,
)
from apps.broadcasts.sanitizer import (
    plain_text_length,
    render_broadcast_message_html,
    sanitize_broadcast_html,
)

# Telegram Bot API's real limits (CLAUDE.md: must be respected exactly).
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
TEXT_ONLY_LIMIT = 4096
MEDIA_CAPTION_LIMIT = 1024


def _validate_media_file_size(uploaded_file):
    """Shared by BroadcastMediaSerializer and PlatformBroadcastMediaSerializer
    so the two composers can never silently drift apart on Telegram's real
    upload limits."""
    content_type = uploaded_file.content_type or ""
    if content_type.startswith("image/"):
        if uploaded_file.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError(
                f"Rasm hajmi {MAX_IMAGE_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
    elif content_type.startswith("video/"):
        if uploaded_file.size > MAX_VIDEO_BYTES:
            raise serializers.ValidationError(
                f"Video hajmi {MAX_VIDEO_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
    else:
        raise serializers.ValidationError("Faqat rasm yoki video fayl yuklash mumkin.")


def _validate_composer_length(title, body, media):
    """Shared by BroadcastSerializer and PlatformBroadcastSerializer. Measures
    the exact string that will be sent (title rendered bold above the body) —
    apps.broadcasts.tasks builds the same string, so validation here and the
    real send can never disagree."""
    limit = MEDIA_CAPTION_LIMIT if media else TEXT_ONLY_LIMIT
    length = plain_text_length(render_broadcast_message_html(title, body))
    if length > limit:
        scope = "media biriktirilganda" if media else "media biriktirilmaganda"
        raise serializers.ValidationError(
            {
                "body": (
                    f"Xabar matni {limit} belgidan oshmasligi kerak ({scope} chegara). "
                    f"Hozirgi uzunlik: {length}."
                )
            }
        )


class BroadcastMediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = BroadcastMedia
        fields = [
            "id",
            "file",
            "media_type",
            "original_filename",
            "size_bytes",
            "url",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "media_type",
            "original_filename",
            "size_bytes",
            "url",
            "created_at",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def get_url(self, obj) -> str:
        # Deliberately not MEDIA_URL — this path always goes through
        # BroadcastMediaFileView, which re-checks tenant scope via the
        # queryset before ever opening the file (CLAUDE.md §4).
        return reverse("broadcast-media-file", kwargs={"pk": obj.pk})

    def validate_file(self, uploaded_file):
        _validate_media_file_size(uploaded_file)
        return uploaded_file


class BroadcastSerializer(serializers.ModelSerializer):
    """`body` is raw editor HTML coming in and sanitized Telegram-safe HTML
    going out (apps.broadcasts.sanitizer) — length is validated against
    Telegram's real limits on the *sanitized* text, since that's what
    actually gets sent (1024 chars with media attached, 4096 without)."""

    media = BroadcastMediaSerializer(read_only=True)
    # `queryset=BroadcastMedia.objects` (the manager, not `.all()`): DRF only
    # calls `.all()`/`.get()` on it lazily at validation time, when the
    # request's tenant context is actually bound — matches the same pattern
    # SellerSerializer.branch uses for the same reason.
    media_id = serializers.PrimaryKeyRelatedField(
        source="media", queryset=BroadcastMedia.objects, required=False, allow_null=True
    )

    class Meta:
        model = Broadcast
        fields = [
            "id",
            "title",
            "body",
            "media",
            "media_id",
            "status",
            "sent_count",
            "failed_count",
            "created_at",
            "sent_at",
        ]
        read_only_fields = ["id", "status", "sent_count", "failed_count", "created_at", "sent_at"]

    def validate_body(self, value):
        return sanitize_broadcast_html(value)

    def validate(self, attrs):
        if self.instance is not None and self.instance.status != Broadcast.Status.DRAFT:
            raise serializers.ValidationError(
                "Faqat qoralama (draft) xabarnomani tahrirlash mumkin."
            )

        title = attrs.get("title", getattr(self.instance, "title", "") if self.instance else "")
        body = attrs.get("body", getattr(self.instance, "body", "") if self.instance else "")
        if "media" in attrs:
            media = attrs["media"]
        else:
            media = getattr(self.instance, "media", None) if self.instance else None

        _validate_composer_length(title, body, media)
        return attrs


class PlatformBroadcastMediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = PlatformBroadcastMedia
        fields = [
            "id",
            "file",
            "media_type",
            "original_filename",
            "size_bytes",
            "url",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "media_type",
            "original_filename",
            "size_bytes",
            "url",
            "created_at",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def get_url(self, obj) -> str:
        return reverse("platform-broadcast-media-file", kwargs={"pk": obj.pk})

    def validate_file(self, uploaded_file):
        _validate_media_file_size(uploaded_file)
        return uploaded_file


class PlatformBroadcastSerializer(serializers.ModelSerializer):
    """Superadmin's platform-wide composer — same shape/limits as
    BroadcastSerializer, fanned out to every tenant on send (see
    apps.broadcasts.tasks.send_platform_broadcast). `sent_count`/
    `failed_count`/`tenant_count` are read-only ints sourced from queryset
    annotations set by PlatformBroadcastViewSet.get_queryset, never computed
    here — see that view for why (touching `.tenant_legs` directly on an
    instance is a tenant-isolation trap, not just an N+1)."""

    media = PlatformBroadcastMediaSerializer(read_only=True)
    media_id = serializers.PrimaryKeyRelatedField(
        source="media",
        queryset=PlatformBroadcastMedia.objects.all(),
        required=False,
        allow_null=True,
    )
    sent_count = serializers.IntegerField(read_only=True)
    failed_count = serializers.IntegerField(read_only=True)
    tenant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PlatformBroadcast
        fields = [
            "id",
            "title",
            "body",
            "media",
            "media_id",
            "status",
            "sent_count",
            "failed_count",
            "tenant_count",
            "created_at",
            "sent_at",
        ]
        read_only_fields = ["id", "status", "created_at", "sent_at"]

    def validate_body(self, value):
        return sanitize_broadcast_html(value)

    def validate(self, attrs):
        if self.instance is not None and self.instance.status != PlatformBroadcast.Status.DRAFT:
            raise serializers.ValidationError(
                "Faqat qoralama (draft) xabarnomani tahrirlash mumkin."
            )

        title = attrs.get("title", getattr(self.instance, "title", "") if self.instance else "")
        body = attrs.get("body", getattr(self.instance, "body", "") if self.instance else "")
        if "media" in attrs:
            media = attrs["media"]
        else:
            media = getattr(self.instance, "media", None) if self.instance else None

        _validate_composer_length(title, body, media)
        return attrs
