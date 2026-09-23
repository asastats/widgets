"""Module containing Real-time refresh widget's URL configurations."""

from django.urls import re_path

from .views import LiveRefreshView, LiveRegroupView

urlpatterns = [
    # The venue groups whose positions changed. Before the poll's own pattern,
    # which would otherwise never let `regroup` past: `\w` does not match the
    # slash, but a 40-character value followed by one is not what the poll
    # matches either, and ordering this first says which is meant rather than
    # relying on that.
    #
    # POST rather than GET because the page sends what it is carrying, which is
    # one line per position and belongs in a body.
    re_path(
        r"^(\w{40}|\w{58})/regroup$",
        LiveRegroupView.as_view(),
        name="liverefresh-regroup",
    ),
    # The poll, for an address or bundle page. Same shape as every other
    # widget's entry: 40 characters is a bundle hash, 58 an address.
    re_path(r"^(\w{40}|\w{58})$", LiveRefreshView.as_view(), name="liverefresh"),
]
