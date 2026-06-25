"""Module containing Haystack router widget's URL configurations."""

from django.urls import re_path

from .views import HaystackAssetsView, HaystackHoldingsView, HaystackSwapView

urlpatterns = [
    # Target-asset search (htmx); must precede the address pattern.
    re_path(r"^assets$", HaystackAssetsView.as_view(), name="haystack_assets"),
    # Fresh holdings for one linked address (htmx panel).
    re_path(
        r"^(\w{58})/holdings$",
        HaystackHoldingsView.as_view(),
        name="haystack_holdings",
    ),
    # Swap shell (bundle or address); execution gated to the linked active address.
    re_path(r"^(\w{40}|\w{58})$", HaystackSwapView.as_view(), name="haystack"),
]
