"""Module containing HOGSWAP router widget's URL configurations."""

from django.urls import re_path

from .views import HogswapSwapView

urlpatterns = [
    # Swap shell, for a bundle or an address; execution is gated to the linked
    # active address in the browser. The holdings and asset-search partials are
    # router-agnostic and mounted once by `widgets.inhouse.swapcore.urls`.
    #
    # **The pattern name must be the widget id.**
    # `widgethost.registry.swap_entry_url` reverses a router's shell by its own
    # id, so a mismatch makes the router selectable in settings and unreachable
    # from the swap button.
    re_path(r"^(\w{40}|\w{58})$", HogswapSwapView.as_view(), name="hogswap"),
]
