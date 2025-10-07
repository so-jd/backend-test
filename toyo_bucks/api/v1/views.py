"""
API views for Toyo Bucks v1.
"""

import logging

from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from toyo_bucks.models import (
    CourseUnitReward,
    RewardClaim,
    ToyoBucksAccount,
    ToyoBucksTransaction,
)

from .serializers import (
    ClaimRewardRequestSerializer,
    ClaimRewardResponseSerializer,
    CourseUnitRewardSerializer,
    RewardClaimSerializer,
    ToyoBucksAccountSerializer,
    ToyoBucksTransactionSerializer,
)

log = logging.getLogger(__name__)


class ToyoBucksAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ToyoBucksAccount.

    Provides endpoints to view user's Toyo Bucks account information.
    """

    serializer_class = ToyoBucksAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return only the current user's account."""
        return ToyoBucksAccount.objects.filter(user=self.request.user).prefetch_related(
            "transactions"
        )

    @action(detail=False, methods=["get"])
    def my_account(self, request):
        """
        Get the current user's Toyo Bucks account.

        Returns:
            Account information including balance and statistics
        """
        account = ToyoBucksAccount.get_or_create_for_user(request.user)
        serializer = self.get_serializer(account)
        return Response(serializer.data)


class ToyoBucksTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ToyoBucksTransaction.

    Provides endpoints to view transaction history.
    """

    serializer_class = ToyoBucksTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return only the current user's transactions."""
        return ToyoBucksTransaction.objects.filter(
            account__user=self.request.user
        ).select_related("account__user")

    @action(detail=False, methods=["get"])
    def my_transactions(self, request):
        """
        Get the current user's transaction history.

        Query parameters:
            - limit: Maximum number of transactions to return (default: 50)
            - transaction_type: Filter by transaction type

        Returns:
            List of transactions
        """
        queryset = self.get_queryset()

        # Apply filters
        transaction_type = request.query_params.get("transaction_type")
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)

        # Apply limit
        limit = request.query_params.get("limit", 50)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except (ValueError, TypeError):
            queryset = queryset[:50]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class RewardClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for RewardClaim.

    Provides endpoints to view claimed rewards and claim new rewards.
    """

    serializer_class = RewardClaimSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return only the current user's reward claims."""
        return RewardClaim.objects.filter(user=self.request.user).select_related("user")

    @action(detail=False, methods=["get"])
    def my_claims(self, request):
        """
        Get the current user's reward claims.

        Returns:
            List of claimed rewards
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def claim(self, request):
        """
        Claim a reward for completing a unit.

        Request body:
            - unit_key: The usage key of the completed unit

        Returns:
            Success status, reward amount, and new balance
        """
        request_serializer = ClaimRewardRequestSerializer(data=request.data)

        if not request_serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Invalid request data",
                    "errors": request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        unit_key_str = request_serializer.validated_data["unit_key"]

        # Parse the unit key
        try:
            unit_key = UsageKey.from_string(unit_key_str)
        except InvalidKeyError:
            return Response(
                {
                    "success": False,
                    "message": f"Invalid unit key: {unit_key_str}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already claimed
        if RewardClaim.has_claimed(request.user, unit_key):
            account = ToyoBucksAccount.objects.get(user=request.user)
            response_serializer = ClaimRewardResponseSerializer(
                {
                    "success": False,
                    "message": "Reward already claimed for this unit",
                    "already_claimed": True,
                    "new_balance": account.balance,
                }
            )
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        # Get reward amount for this unit
        reward_amount = CourseUnitReward.get_reward_for_unit(unit_key)

        if reward_amount is None:
            return Response(
                {
                    "success": False,
                    "message": "No reward configured for this unit",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Claim the reward
        try:
            claim = RewardClaim.claim_reward(request.user, unit_key, reward_amount)

            if claim is None:
                # Already claimed (race condition)
                account = ToyoBucksAccount.objects.get(user=request.user)
                response_serializer = ClaimRewardResponseSerializer(
                    {
                        "success": False,
                        "message": "Reward already claimed for this unit",
                        "already_claimed": True,
                        "new_balance": account.balance,
                    }
                )
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            account = ToyoBucksAccount.objects.get(user=request.user)
            response_serializer = ClaimRewardResponseSerializer(
                {
                    "success": True,
                    "message": "Reward claimed successfully",
                    "reward_amount": reward_amount,
                    "new_balance": account.balance,
                    "already_claimed": False,
                }
            )
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            log.exception(f"Error claiming reward for user {request.user.username}: {e}")
            return Response(
                {
                    "success": False,
                    "message": f"Error claiming reward: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CourseUnitRewardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for CourseUnitReward.

    Provides endpoints to view configured rewards for units.
    Staff only for full CRUD.
    """

    serializer_class = CourseUnitRewardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return active rewards."""
        return CourseUnitReward.objects.filter(is_active=True)

    @action(detail=False, methods=["get"])
    def by_course(self, request):
        """
        Get all rewards for a specific course.

        Query parameters:
            - course_key: The course key to filter by

        Returns:
            List of unit rewards for the course
        """
        course_key = request.query_params.get("course_key")

        if not course_key:
            return Response(
                {"error": "course_key parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.get_queryset().filter(course_key=course_key)
        serializer = self.get_serializer(queryset, many=True)

        total_rewards = CourseUnitReward.get_total_course_rewards(course_key)

        return Response(
            {
                "course_key": course_key,
                "total_possible_rewards": float(total_rewards),
                "unit_rewards": serializer.data,
            }
        )

    @action(detail=False, methods=["get"])
    def by_unit(self, request):
        """
        Get reward information for a specific unit.

        Query parameters:
            - unit_key: The unit usage key

        Returns:
            Reward information for the unit
        """
        unit_key_str = request.query_params.get("unit_key")

        if not unit_key_str:
            return Response(
                {"error": "unit_key parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            unit_key = UsageKey.from_string(unit_key_str)
        except InvalidKeyError:
            return Response(
                {"error": f"Invalid unit key: {unit_key_str}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reward = CourseUnitReward.objects.get(unit_key=unit_key, is_active=True)
            serializer = self.get_serializer(reward)

            # Check if user has claimed this reward
            has_claimed = RewardClaim.has_claimed(request.user, unit_key)

            return Response(
                {
                    **serializer.data,
                    "has_claimed": has_claimed,
                }
            )
        except CourseUnitReward.DoesNotExist:
            return Response(
                {
                    "unit_key": unit_key_str,
                    "reward_amount": None,
                    "has_claimed": False,
                    "message": "No reward configured for this unit",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
