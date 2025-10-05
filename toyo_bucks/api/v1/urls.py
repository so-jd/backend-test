"""
URL configuration for Toyo Bucks API v1.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CourseUnitRewardViewSet,
    RewardClaimViewSet,
    ToyoBucksAccountViewSet,
    ToyoBucksTransactionViewSet,
)

app_name = "toyo_bucks_v1"

router = DefaultRouter()
router.register(r"accounts", ToyoBucksAccountViewSet, basename="account")
router.register(r"transactions", ToyoBucksTransactionViewSet, basename="transaction")
router.register(r"claims", RewardClaimViewSet, basename="claim")
router.register(r"rewards", CourseUnitRewardViewSet, basename="reward")

urlpatterns = [
    path("", include(router.urls)),
]
