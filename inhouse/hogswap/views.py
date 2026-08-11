"""HOGSWAP router widget's views.

The holdings and asset partials are served once by the shared swap-core widget
(``swap_holdings`` / ``swap_assets``), so only the router-specific shell view
lives here. It subclasses the shared ``BaseSwapShellView`` and contributes this
router's template plus its non-secret client config.

**This widget earns nothing, and that is not an oversight.** Folks takes a
``feeBps`` with our ``referrer`` and Haystack credits a ``referrerAddress``;
HOGSWAP's SDK has no referral parameter at all, so there is nowhere to name
ourselves. What the user pays is HOGSWAP's own 5 basis points, waived in
proportion to the HOG they hold and free at 100 - which is a property of the
caller's wallet rather than of the trade, and is why the manifest's
``revenue_account`` is empty in fact and not only by convention.
"""

from django.conf import settings
from widgethost.swap_views import BaseSwapShellView

from .manifest import MANIFEST


class HogswapSwapView(BaseSwapShellView):
    """Render the HOGSWAP swap shell. Carries the non-secret client config.

    :var template_name: relative path to the Django template
    :var manifest: this widget's parsed manifest
    """

    template_name = "hogswap/index.html"
    manifest = MANIFEST

    def client_cfg_context(self):
        """Non-secret HOGSWAP client config for the shell.

        Both values are optional and both are empty by default. ``base_url``
        exists so a staging deployment can point at another host without a code
        change; empty means the SDK's own default. ``api_key`` is HOGSWAP's
        ``hsk_`` rate-limit key for its paid tier - like Haystack's it is a
        throughput key rather than a fund-access secret, so it is necessarily
        visible client-side, and the free tier needs none.

        :return: dict
        """
        return {
            "hogswap_base_url": getattr(settings, "HOGSWAP_BASE_URL", ""),
            "hogswap_api_key": getattr(settings, "HOGSWAP_API_KEY", ""),
        }
