from django.urls import reverse
from PIL import Image, UnidentifiedImageError
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

# Explicit allowlist, not a startswith("image/")/startswith("video/") check
# (audit finding H-1): the old check let ANY client-declared image/* or
# video/* Content-Type through — including image/svg+xml, which this app
# then served back with that same declared type and Content-Disposition:
# inline, i.e. a browser would execute a <script> embedded in an "image"
# upload in this app's own origin. Every type below is one Telegram's Bot
# API and every mainstream browser render as inert raster/video data, never
# as markup.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


def _verify_image(uploaded_file) -> None:
    """Decoder-level check, not just a Content-Type string match: Pillow has
    no SVG plugin, so a mislabeled/renamed SVG (or any non-image bytes)
    fails here even if it somehow claimed an allowed image Content-Type.
    Image.verify() is the standard Pillow pattern for validating untrusted
    input without doing the extra work of a full pixel decode."""
    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise serializers.ValidationError("Fayl haqiqiy rasm emas.") from exc
    finally:
        uploaded_file.seek(0)


def _looks_like_real_video(head: bytes) -> bool:
    """Cheap, dependency-free container-signature check on the file's first
    bytes: an ISO base media 'ftyp' box (MP4/MOV) or a WebM/Matroska EBML
    header. Not a full parse — nothing here validates codecs/streams — but
    it's enough to reject a renamed non-video payload (e.g. an HTML/SVG
    file with a spoofed video/* Content-Type)."""
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    return head[:4] == b"\x1a\x45\xdf\xa3"


def _validate_media_file_size(uploaded_file):
    """Shared by BroadcastMediaSerializer and PlatformBroadcastMediaSerializer
    so the two composers can never silently drift apart on Telegram's real
    upload limits or on what actually counts as "an image"/"a video" here."""
    content_type = uploaded_file.content_type or ""
    if content_type in ALLOWED_IMAGE_TYPES:
        if uploaded_file.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError(
                f"Rasm hajmi {MAX_IMAGE_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
        _verify_image(uploaded_file)
    elif content_type in ALLOWED_VIDEO_TYPES:
        if uploaded_file.size > MAX_VIDEO_BYTES:
            raise serializers.ValidationError(
                f"Video hajmi {MAX_VIDEO_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
            )
        uploaded_file.seek(0)
        head = uploaded_file.read(64)
        uploaded_file.seek(0)
        if not _looks_like_real_video(head):
            raise serializers.ValidationError("Fayl haqiqiy video emas.")
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
