from rest_framework import serializers

from apps.ledger.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id",
            "branch",
            "customer",
            "seller",
            "check_amount",
            "cashback_earned",
            "cashback_spent",
            "cash_paid",
            "cashback_rate",
            "type",
            "status",
            "reverses",
            "no_cashback",
            "flagged",
            "created_at",
        ]
        read_only_fields = fields


class ReversalRequestSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField()
