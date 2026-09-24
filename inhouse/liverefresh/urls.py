"""Module containing Real-time refresh widget's URL configurations."""

from django.urls import re_path

from .views import LiveRefreshView, LiveRegroupView

urlpatterns = [
    # The venue groups whose positions changed. **Before the poll's pattern**,
    # so the ordering says which is meant rather than relying on `\w` not
    # matching a slash. POST because the page sends one line per position,
    # which belongs in a body.
    re_path(
        r"^(\w{40}|\w{58})/regroup$",
        LiveRegroupView.as_view(),
        name="liverefresh-regroup",
    ),
    # The poll, for an address or bundle page. Same shape as every other
    # widget's entry: 40 characters is a bundle hash, 58 an address.
    re_path(r"^(\w{40}|\w{58})$", LiveRefreshView.as_view(), name="liverefresh"),
]
