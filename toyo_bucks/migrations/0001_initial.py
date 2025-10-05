"""
Initial migration for Toyo Bucks models.
"""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import model_utils.fields
import opaque_keys.edx.django.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial migration for Toyo Bucks."""

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ToyoBucksAccount",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "balance",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Current balance of Toyo Bucks",
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        help_text="The user who owns this Toyo Bucks account",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="toyo_bucks_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Toyo Bucks Account",
                "verbose_name_plural": "Toyo Bucks Accounts",
                "db_table": "toyo_bucks_account",
            },
        ),
        migrations.CreateModel(
            name="ToyoBucksTransaction",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Transaction amount (positive for credit, negative for debit)",
                        max_digits=10,
                    ),
                ),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("unit_completion", "Unit Completion Reward"),
                            ("manual_adjustment", "Manual Adjustment"),
                            ("store_purchase", "Store Purchase"),
                            ("bonus", "Bonus"),
                            ("refund", "Refund"),
                        ],
                        db_index=True,
                        help_text="Type of transaction",
                        max_length=50,
                    ),
                ),
                (
                    "balance_after",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Account balance after this transaction",
                        max_digits=10,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, help_text="Optional description of the transaction"
                    ),
                ),
                (
                    "reference_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Optional reference ID to related object (e.g., unit usage key)",
                        max_length=255,
                    ),
                ),
                (
                    "account",
                    models.ForeignKey(
                        help_text="The account this transaction belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="toyo_bucks.ToyoBucksAccount",
                    ),
                ),
            ],
            options={
                "verbose_name": "Toyo Bucks Transaction",
                "verbose_name_plural": "Toyo Bucks Transactions",
                "db_table": "toyo_bucks_transaction",
                "ordering": ["-created"],
            },
        ),
        migrations.CreateModel(
            name="CourseUnitReward",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "course_key",
                    opaque_keys.edx.django.models.CourseKeyField(
                        db_index=True,
                        help_text="The course this reward applies to",
                        max_length=255,
                    ),
                ),
                (
                    "unit_key",
                    opaque_keys.edx.django.models.UsageKeyField(
                        db_index=True,
                        help_text="The specific unit (block) this reward applies to",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "reward_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("10.00"),
                        help_text="Amount of Toyo Bucks to award for completing this unit",
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Whether this reward is currently active",
                    ),
                ),
            ],
            options={
                "verbose_name": "Course Unit Reward",
                "verbose_name_plural": "Course Unit Rewards",
                "db_table": "toyo_bucks_course_unit_reward",
            },
        ),
        migrations.CreateModel(
            name="RewardClaim",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "unit_key",
                    opaque_keys.edx.django.models.UsageKeyField(
                        db_index=True,
                        help_text="The unit (block) for which the reward was claimed",
                        max_length=255,
                    ),
                ),
                (
                    "reward_amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Amount of Toyo Bucks awarded",
                        max_digits=10,
                    ),
                ),
                (
                    "transaction",
                    models.OneToOneField(
                        blank=True,
                        help_text="The transaction that awarded these Toyo Bucks",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reward_claim",
                        to="toyo_bucks.ToyoBucksTransaction",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="The user who claimed this reward",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="toyo_bucks_claims",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Reward Claim",
                "verbose_name_plural": "Reward Claims",
                "db_table": "toyo_bucks_reward_claim",
            },
        ),
        migrations.AddIndex(
            model_name="toyobuckstransaction",
            index=models.Index(
                fields=["-created", "account"], name="toyo_bucks__created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="rewardclaim",
            index=models.Index(
                fields=["user", "unit_key"], name="toyo_bucks__user_id_idx"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="rewardclaim",
            unique_together={("user", "unit_key")},
        ),
    ]
