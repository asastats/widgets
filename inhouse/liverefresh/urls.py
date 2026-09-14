"""Module containing Real-time refresh widget's URL configurations."""

from django.urls import re_path

from .views import LiveRefreshView

urlpatterns = [
    # The poll, for an address or bundle page. Same shape as every other
    # widget's entry: 40 characters is a bundle hash, 58 an address.
    re_path(r"^(\w{40}|\w{58})$", LiveRefreshView.as_view(), name="liverefresh"),
]
