"""
Django admin interface for Toyo Bucks models.
"""

from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    CourseUnitReward,
    RewardClaim,
    ToyoBucksAccount,
    ToyoBucksTransaction,
)


@admin.register(ToyoBucksAccount)
class ToyoBucksAccountAdmin(admin.ModelAdmin):
    """Admin interface for ToyoBucksAccount model."""

    list_display = (
        "user",
        "balance",
        "total_earned",
        "total_spent",
        "transaction_count",
        "created",
        "modified",
    )
    list_filter = ("created", "modified")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created", "modified", "total_earned", "total_spent", "transaction_count")

    fieldsets = (
        (None, {
            "fields": ("user", "balance")
        }),
        (_("Statistics"), {
            "fields": ("total_earned", "total_spent", "transaction_count"),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with annotations."""
        qs = super().get_queryset(request)
        qs = qs.select_related("user")
        return qs

    def total_earned(self, obj):
        """Calculate total Toyo Bucks earned."""
        total = obj.transactions.filter(amount__gt=0).aggregate(total=Sum("amount"))
        return total["total"] or 0
    total_earned.short_description = _("Total Earned")

    def total_spent(self, obj):
        """Calculate total Toyo Bucks spent."""
        total = obj.transactions.filter(amount__lt=0).aggregate(total=Sum("amount"))
        return abs(total["total"]) if total["total"] else 0
    total_spent.short_description = _("Total Spent")

    def transaction_count(self, obj):
        """Count total transactions."""
        return obj.transactions.count()
    transaction_count.short_description = _("Transactions")


@admin.register(ToyoBucksTransaction)
class ToyoBucksTransactionAdmin(admin.ModelAdmin):
    """Admin interface for ToyoBucksTransaction model."""

    list_display = (
        "id",
        "user_display",
        "amount_display",
        "transaction_type",
        "balance_after",
        "created",
    )
    list_filter = ("transaction_type", "created")
    search_fields = (
        "account__user__username",
        "account__user__email",
        "description",
        "reference_id",
    )
    readonly_fields = (
        "account",
        "amount",
        "transaction_type",
        "balance_after",
        "description",
        "reference_id",
        "created",
        "modified",
    )
    date_hierarchy = "created"

    fieldsets = (
        (None, {
            "fields": ("account", "amount", "transaction_type", "balance_after")
        }),
        (_("Details"), {
            "fields": ("description", "reference_id"),
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        """Disable adding transactions through admin (should be created programmatically)."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting transactions to maintain audit trail."""
        return False

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        qs = super().get_queryset(request)
        qs = qs.select_related("account__user")
        return qs

    def user_display(self, obj):
        """Display the username."""
        return obj.account.user.username
    user_display.short_description = _("User")
    user_display.admin_order_field = "account__user__username"

    def amount_display(self, obj):
        """Display amount with color coding."""
        if obj.amount > 0:
            color = "green"
            prefix = "+"
        else:
            color = "red"
            prefix = ""
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{:.2f} TB</span>',
            color,
            prefix,
            obj.amount,
        )
    amount_display.short_description = _("Amount")
    amount_display.admin_order_field = "amount"


@admin.register(CourseUnitReward)
class CourseUnitRewardAdmin(admin.ModelAdmin):
    """Admin interface for CourseUnitReward model."""

    list_display = (
        "unit_key",
        "course_key",
        "reward_amount",
        "is_active",
        "created",
        "modified",
    )
    list_filter = ("is_active", "created", "modified")
    search_fields = ("course_key", "unit_key")
    list_editable = ("reward_amount", "is_active")

    fieldsets = (
        (None, {
            "fields": ("course_key", "unit_key", "reward_amount", "is_active")
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )

    readonly_fields = ("created", "modified")

    actions = ["activate_rewards", "deactivate_rewards"]

    def activate_rewards(self, request, queryset):
        """Bulk activate selected rewards."""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _(f"{updated} reward(s) successfully activated."),
        )
    activate_rewards.short_description = _("Activate selected rewards")

    def deactivate_rewards(self, request, queryset):
        """Bulk deactivate selected rewards."""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _(f"{updated} reward(s) successfully deactivated."),
        )
    deactivate_rewards.short_description = _("Deactivate selected rewards")


@admin.register(RewardClaim)
class RewardClaimAdmin(admin.ModelAdmin):
    """Admin interface for RewardClaim model."""

    list_display = (
        "id",
        "user",
        "unit_key",
        "reward_amount",
        "created",
    )
    list_filter = ("created",)
    search_fields = ("user__username", "user__email", "unit_key")
    readonly_fields = (
        "user",
        "unit_key",
        "reward_amount",
        "transaction",
        "created",
        "modified",
    )
    date_hierarchy = "created"

    fieldsets = (
        (None, {
            "fields": ("user", "unit_key", "reward_amount", "transaction")
        }),
        (_("Timestamps"), {
            "fields": ("created", "modified"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        """Disable adding claims through admin (should be created programmatically)."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting claims to maintain audit trail."""
        return False

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        qs = super().get_queryset(request)
        qs = qs.select_related("user", "transaction")
        return qs
