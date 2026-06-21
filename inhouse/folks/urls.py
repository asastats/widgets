"""Module containing Folks smart router widget's URL configurations."""

from django.urls import re_path

from .views import FolksAssetsView, FolksHoldingsView, FolksSwapView

urlpatterns = [
    # Target-asset search (htmx); must precede the address pattern.
    re_path(r"^assets$", FolksAssetsView.as_view(), name="folks_assets"),
    # Fresh holdings for one linked address (htmx panel).
    re_path(r"^(\w{58})/holdings$", FolksHoldingsView.as_view(), name="folks_holdings"),
    # Swap shell. Page context may be a bundle; execution is gated to the single
    # linked + active address in the browser.
    re_path(r"^(\w{40}|\w{58})$", FolksSwapView.as_view(), name="folks"),
]
