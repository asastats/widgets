"""Module containing Haystack order router widget's URL configurations."""

from django.urls import re_path

from .views import HaystackSwapView

urlpatterns = [
    # Swap shell (bundle or address); execution is gated to the linked active
    # address in the browser. The holdings/asset-search partials are now shared,
    # router-agnostic routes (swap_holdings / swap_assets), mounted once by
    # widgets.inhouse.swapcore.urls.
    re_path(r"^(\w{40}|\w{58})$", HaystackSwapView.as_view(), name="haystack"),
]
