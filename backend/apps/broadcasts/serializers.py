from rest_framework import serializers

from apps.broadcasts.models import Broadcast


class BroadcastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broadcast
        fields = [
            "id",
            "title",
            "body",
            "status",
            "sent_count",
            "failed_count",
            "created_at",
        ]
        read_only_fields = ["id", "status", "sent_count", "failed_count", "created_at"]
