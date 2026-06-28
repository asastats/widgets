"""Module containing Folks smart router widget's URL configurations."""

from django.urls import re_path

from .views import FolksSwapView

urlpatterns = [
    # Swap shell. Page context may be a bundle; execution is gated to the single
    # linked + active address in the browser. The holdings/asset-search partials
    # are now shared, router-agnostic routes (see widgets.inhouse.swapcore.urls:
    # swap_holdings / swap_assets), mounted once.
    re_path(r"^(\w{40}|\w{58})$", FolksSwapView.as_view(), name="folks"),
]
