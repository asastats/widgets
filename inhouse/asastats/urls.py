"""Module containing ASA Stats smart router widget's URL configurations."""

from django.urls import re_path

from .views import AsastatsGroupView, AsastatsQuoteView, AsastatsSwapView

urlpatterns = [
    # Quote and group building. Both are this router's own, because unlike
    # Folks and Haystack there is no browser SDK to call - the routing runs in
    # the engine and these proxy to it under the widget's declared scopes.
    re_path(r"^quote$", AsastatsQuoteView.as_view(), name="asastats_quote"),
    re_path(r"^group$", AsastatsGroupView.as_view(), name="asastats_group"),
    # Swap shell. Must come last: the patterns above would otherwise be
    # swallowed by the address/bundle pattern.
    re_path(r"^(\w{40}|\w{58})$", AsastatsSwapView.as_view(), name="asastats"),
]
