"""Shared, router-agnostic swap engine-data URLs (mounted once).

These replace the per-router ``<router_id>_holdings`` / ``<router_id>_assets``
patterns. The router-specific shell page keeps its own URL in each router widget.
"""

from django.urls import re_path

from .views import SwapAssetsView, SwapHoldingsView

urlpatterns = [
    # Target-asset search (htmx); must precede the address pattern if co-mounted.
    re_path(r"^assets$", SwapAssetsView.as_view(), name="swap_assets"),
    # Fresh holdings for one linked address (htmx panel).
    re_path(
        r"^(\w{58})/holdings$", SwapHoldingsView.as_view(), name="swap_holdings"
    ),
]
