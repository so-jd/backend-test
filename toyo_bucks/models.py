"""
Database models for Toyo Bucks in-app currency system.
"""

import logging
from decimal import Decimal

from django.contrib import auth
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField

log = logging.getLogger(__name__)

User = auth.get_user_model()


class ToyoBucksAccount(TimeStampedModel):
    """
    Represents a user's Toyo Bucks account balance.

    .. no_pii:
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="toyo_bucks_account",
        help_text=_("The user who owns this Toyo Bucks account"),
    )
    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Current balance of Toyo Bucks"),
    )

    class Meta:
        """Model options."""

        verbose_name = _("Toyo Bucks Account")
        verbose_name_plural = _("Toyo Bucks Accounts")
        db_table = "toyo_bucks_account"

    def __str__(self):
        """User-friendly string representation of this model."""
        return f"{self.user.username}: {self.balance} Toyo Bucks"

    @classmethod
    def get_or_create_for_user(cls, user):
        """
        Get or create an account for the given user.

        Args:
            user: The user to get or create an account for

        Returns:
            ToyoBucksAccount: The user's account
        """
        account, created = cls.objects.get_or_create(user=user)
        if created:
            log.info(f"Created Toyo Bucks account for user {user.username}")
        return account

    def add_balance(self, amount, transaction_type, description="", reference_id=None):
        """
        Add balance to the account and create a transaction record.

        Args:
            amount: The amount to add (Decimal)
            transaction_type: The type of transaction
            description: Optional description
            reference_id: Optional reference to related object

        Returns:
            ToyoBucksTransaction: The created transaction
        """
        if amount < 0:
            raise ValueError("Amount must be positive when adding balance")

        self.balance += Decimal(str(amount))
        self.save()

        transaction = ToyoBucksTransaction.objects.create(
            account=self,
            amount=amount,
            transaction_type=transaction_type,
            balance_after=self.balance,
            description=description,
            reference_id=reference_id,
        )

        log.info(
            f"Added {amount} Toyo Bucks to {self.user.username}'s account. "
            f"New balance: {self.balance}"
        )

        return transaction

    def deduct_balance(self, amount, transaction_type, description="", reference_id=None):
        """
        Deduct balance from the account and create a transaction record.

        Args:
            amount: The amount to deduct (Decimal)
            transaction_type: The type of transaction
            description: Optional description
            reference_id: Optional reference to related object

        Returns:
            ToyoBucksTransaction: The created transaction

        Raises:
            ValueError: If insufficient balance
        """
        if amount < 0:
            raise ValueError("Amount must be positive when deducting balance")

        if self.balance < Decimal(str(amount)):
            raise ValueError(
                f"Insufficient balance. Current: {self.balance}, Required: {amount}"
            )

        self.balance -= Decimal(str(amount))
        self.save()

        transaction = ToyoBucksTransaction.objects.create(
            account=self,
            amount=-amount,
            transaction_type=transaction_type,
            balance_after=self.balance,
            description=description,
            reference_id=reference_id,
        )

        log.info(
            f"Deducted {amount} Toyo Bucks from {self.user.username}'s account. "
            f"New balance: {self.balance}"
        )

        return transaction


class ToyoBucksTransaction(TimeStampedModel):
    """
    Records a transaction in a Toyo Bucks account.

    .. no_pii:
    """

    TRANSACTION_TYPE_CHOICES = [
        ("unit_completion", _("Unit Completion Reward")),
        ("manual_adjustment", _("Manual Adjustment")),
        ("store_purchase", _("Store Purchase")),
        ("bonus", _("Bonus")),
        ("refund", _("Refund")),
    ]

    account = models.ForeignKey(
        ToyoBucksAccount,
        on_delete=models.CASCADE,
        related_name="transactions",
        help_text=_("The account this transaction belongs to"),
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Transaction amount (positive for credit, negative for debit)"),
    )
    transaction_type = models.CharField(
        max_length=50,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True,
        help_text=_("Type of transaction"),
    )
    balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Account balance after this transaction"),
    )
    description = models.TextField(
        blank=True,
        help_text=_("Optional description of the transaction"),
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Optional reference ID to related object (e.g., unit usage key)"),
    )

    class Meta:
        """Model options."""

        verbose_name = _("Toyo Bucks Transaction")
        verbose_name_plural = _("Toyo Bucks Transactions")
        db_table = "toyo_bucks_transaction"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["-created", "account"]),
        ]

    def __str__(self):
        """User-friendly string representation of this model."""
        return (
            f"{self.account.user.username}: {self.amount:+.2f} TB "
            f"({self.get_transaction_type_display()})"
        )


class CourseUnitReward(TimeStampedModel):
    """
    Defines the reward amount for completing a specific course unit.

    .. no_pii:
    """

    course_key = CourseKeyField(
        max_length=255,
        db_index=True,
        help_text=_("The course this reward applies to"),
    )
    unit_key = UsageKeyField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("The specific unit (block) this reward applies to"),
    )
    reward_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Amount of Toyo Bucks to award for completing this unit"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this reward is currently active"),
    )

    class Meta:
        """Model options."""

        verbose_name = _("Course Unit Reward")
        verbose_name_plural = _("Course Unit Rewards")
        db_table = "toyo_bucks_course_unit_reward"

    def __str__(self):
        """User-friendly string representation of this model."""
        return f"{self.unit_key}: {self.reward_amount} TB"

    @classmethod
    def get_reward_for_unit(cls, unit_key):
        """
        Get the reward amount for a specific unit.

        Args:
            unit_key: The usage key of the unit

        Returns:
            Decimal: The reward amount, or None if no reward is configured
        """
        try:
            reward = cls.objects.get(unit_key=unit_key, is_active=True)
            return reward.reward_amount
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_total_course_rewards(cls, course_key):
        """
        Calculate total possible Toyo Bucks for a course.

        Args:
            course_key: The course key

        Returns:
            Decimal: Total possible rewards for the course
        """
        total = cls.objects.filter(
            course_key=course_key, is_active=True
        ).aggregate(total=Sum("reward_amount"))
        return total["total"] or Decimal("0.00")


class RewardClaim(TimeStampedModel):
    """
    Tracks which units a user has claimed rewards for.
    Ensures users can only claim rewards once per unit.

    .. no_pii:
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="toyo_bucks_claims",
        help_text=_("The user who claimed this reward"),
    )
    unit_key = UsageKeyField(
        max_length=255,
        db_index=True,
        help_text=_("The unit (block) for which the reward was claimed"),
    )
    reward_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Amount of Toyo Bucks awarded"),
    )
    transaction = models.OneToOneField(
        ToyoBucksTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reward_claim",
        help_text=_("The transaction that awarded these Toyo Bucks"),
    )

    class Meta:
        """Model options."""

        verbose_name = _("Reward Claim")
        verbose_name_plural = _("Reward Claims")
        db_table = "toyo_bucks_reward_claim"
        unique_together = ("user", "unit_key")
        indexes = [
            models.Index(fields=["user", "unit_key"]),
        ]

    def __str__(self):
        """User-friendly string representation of this model."""
        return f"{self.user.username} claimed {self.reward_amount} TB for {self.unit_key}"

    @classmethod
    def has_claimed(cls, user, unit_key):
        """
        Check if a user has already claimed a reward for a unit.

        Args:
            user: The user to check
            unit_key: The unit usage key

        Returns:
            bool: True if already claimed, False otherwise
        """
        return cls.objects.filter(user=user, unit_key=unit_key).exists()

    @classmethod
    def claim_reward(cls, user, unit_key, reward_amount):
        """
        Claim a reward for completing a unit.

        Args:
            user: The user claiming the reward
            unit_key: The unit usage key
            reward_amount: The amount to award

        Returns:
            RewardClaim: The created claim, or None if already claimed

        Raises:
            ValueError: If reward_amount is invalid
        """
        # Check if already claimed
        if cls.has_claimed(user, unit_key):
            log.warning(
                f"User {user.username} already claimed reward for unit {unit_key}"
            )
            return None

        if reward_amount <= 0:
            raise ValueError("Reward amount must be positive")

        # Get or create account
        account = ToyoBucksAccount.get_or_create_for_user(user)

        # Create transaction
        transaction = account.add_balance(
            amount=reward_amount,
            transaction_type="unit_completion",
            description=f"Reward for completing unit",
            reference_id=str(unit_key),
        )

        # Create claim record
        claim = cls.objects.create(
            user=user,
            unit_key=unit_key,
            reward_amount=reward_amount,
            transaction=transaction,
        )

        log.info(
            f"User {user.username} claimed {reward_amount} TB for unit {unit_key}"
        )

        return claim
