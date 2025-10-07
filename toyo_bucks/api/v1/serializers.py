"""
Serializers for Toyo Bucks API v1.
"""

from rest_framework import serializers
from django.db.models import Sum
from decimal import Decimal
from toyo_bucks.models import (
    CourseUnitReward,
    RewardClaim,
    ToyoBucksAccount,
    ToyoBucksTransaction,
)


class ToyoBucksAccountSerializer(serializers.ModelSerializer):
    """Serializer for ToyoBucksAccount model."""

    username = serializers.CharField(source="user.username", read_only=True)
    total_earned = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta:
        model = ToyoBucksAccount
        fields = [
            "id",
            "username",
            "balance",
            "total_earned",
            "total_spent",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "balance", "created", "modified"]

    def get_total_earned(self, obj):
        """Calculate total Toyo Bucks earned."""
        total = obj.transactions.filter(
            transaction_type__in=['unit_completion', 'manual_adjustment', 'bonus', 'refund']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return float(total)

    def get_total_spent(self, obj):
        """Calculate total Toyo Bucks spent."""
        total = obj.transactions.filter(
            transaction_type='store_purchase'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return float(abs(total))


class ToyoBucksTransactionSerializer(serializers.ModelSerializer):
    """Serializer for ToyoBucksTransaction model."""

    username = serializers.CharField(source="account.user.username", read_only=True)

    class Meta:
        model = ToyoBucksTransaction
        fields = [
            "id",
            "username",
            "amount",
            "transaction_type",
            "balance_after",
            "description",
            "reference_id",
            "created",
        ]
        read_only_fields = fields


class CourseUnitRewardSerializer(serializers.ModelSerializer):
    """Serializer for CourseUnitReward model."""

    class Meta:
        model = CourseUnitReward
        fields = [
            "id",
            "course_key",
            "unit_key",
            "reward_amount",
            "is_active",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "created", "modified"]


class RewardClaimSerializer(serializers.ModelSerializer):
    """Serializer for RewardClaim model."""

    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = RewardClaim
        fields = [
            "id",
            "username",
            "unit_key",
            "reward_amount",
            "created",
        ]
        read_only_fields = fields


class ClaimRewardRequestSerializer(serializers.Serializer):
    """Serializer for claiming a reward."""

    unit_key = serializers.CharField(
        required=True,
        help_text="The usage key of the completed unit",
    )


class ClaimRewardResponseSerializer(serializers.Serializer):
    """Serializer for claim reward response."""

    success = serializers.BooleanField()
    message = serializers.CharField()
    reward_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )
    new_balance = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )
    already_claimed = serializers.BooleanField(default=False)
