"""Module containing widgets' URL configurations."""

from django.urls import include, re_path

from constants import INHOUSE_WIDGETS, THIRDPARTY_WIDGETS

try:
    urlpatterns = [
        re_path(rf"^{widget}/", include(f"widgets.inhouse.{widget}.urls"))
        for widget in INHOUSE_WIDGETS
    ] + [
        re_path(rf"^{widget}/", include(f"widgets.thirdparty.{widget}.urls"))
        for widget in THIRDPARTY_WIDGETS
    ]

except ModuleNotFoundError:
    urlpatterns = [
        re_path(rf"^{widget}/", include(f"inhouse.{widget}.urls"))
        for widget in INHOUSE_WIDGETS
    ] + [
        re_path(rf"^{widget}/", include(f"thirdparty.{widget}.urls"))
        for widget in THIRDPARTY_WIDGETS
    ]
