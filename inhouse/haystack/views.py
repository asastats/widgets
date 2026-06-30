"""Haystack order router widget's views.

After endpoint consolidation the holdings + asset partials are served once by the
shared swap-core widget (``swap_holdings`` / ``swap_assets``), so only the
router-specific shell view remains here. It still subclasses the shared
``BaseSwapShellView`` and contributes only this router's template plus its
non-secret client config.
"""

from django.conf import settings
from widgethost.swap_views import BaseSwapShellView

from .manifest import MANIFEST


class HaystackSwapView(BaseSwapShellView):
    """Render the Haystack swap shell. Carries the non-secret client config.

    :var template_name: relative path to the Django template
    :var manifest: this widget's parsed manifest
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
