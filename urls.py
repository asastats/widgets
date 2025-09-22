"""Module containing widgets' URL configurations."""

from django.urls import include, re_path
from django.conf import settings

urlpatterns = [
    re_path(rf"^{widget}/", include(f"widgets.inhouse.{widget}.urls"))
    for widget in settings.INHOUSE_WIDGETS
] + [
    re_path(rf"^{widget}/", include(f"widgets.thirdparty.{widget}.urls"))
    for widget in settings.THIRDPARTY_WIDGETS
]
