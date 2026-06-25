"""Haystack order router widget's views.

Thin subclasses of the shared, router-agnostic base views. The holdings + asset
partials are reused from the folks widget (they are router-agnostic -- the shared
controller reads the same ``id-folks-*`` hooks regardless of router). Only the
shell template and the non-secret client config differ per router.
"""

from django.conf import settings
from widgethost.swap_views import (
    BaseSwapAssetsView,
    BaseSwapHoldingsView,
    BaseSwapShellView,
)

from .manifest import MANIFEST


class HaystackSwapView(BaseSwapShellView):
    """Render the Haystack swap shell. Carries the non-secret client config.

    :var template_name: relative path to the Django template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    template_name = "haystack/index.html"
    manifest = MANIFEST

    def client_cfg_context(self):
        """Non-secret Haystack client config for the shell + marker.

        The API key is a public rate-limit key (free tier), not a fund-access
        secret; it is necessarily visible client-side.

        :return: dict
        """
        return {
            "haystack_referrer": getattr(settings, "HAYSTACK_REFERRER_ADDRESS", ""),
            "haystack_api_key": getattr(settings, "HAYSTACK_API_KEY", ""),
        }


class HaystackHoldingsView(BaseSwapHoldingsView):
    """htmx partial: fresh holdings for one linked address.

    :var template_name: reuses the router-agnostic holdings partial
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    template_name = "folks/_panel.html"
    manifest = MANIFEST


class HaystackAssetsView(BaseSwapAssetsView):
    """htmx partial: ranked asset metadata for the target-asset search.

    :var template_name: reuses the router-agnostic holdings partial
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    template_name = "folks/_assets.html"
    manifest = MANIFEST
