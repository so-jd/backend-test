"""
URL configuration for Toyo Bucks API.
"""

from django.urls import include, path

app_name = "toyo_bucks_api"

urlpatterns = [
    path("v1/", include("toyo_bucks.api.v1.urls")),
]
