"""
URLs for toyo_bucks.
"""

from django.urls import include, path

urlpatterns = [
    path("api/toyo-bucks/", include("toyo_bucks.api.urls")),
]
