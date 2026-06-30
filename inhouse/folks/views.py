"""Module containing Folks smart router widget's views.

Only the router-specific shell page lives here. The router-agnostic engine-data
partials (fresh holdings + asset search) are shared and live in
:mod:`widgets.inhouse.swapcore.views`.
"""

from api.widgets import bundle_and_addresses_from_path
from django.conf import settings
from django.views.generic.base import TemplateView
from walletauth.gating import linked_addresses_for_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST


class FolksSwapView(WidgetAccessMixin, TemplateView):
    """Render the Folks swap widget shell for an address or bundle page.

    Engine-backed: holdings and asset metadata are fetched on demand by the shared
    swap-core htmx partials (``swap_holdings`` / ``swap_assets``), not injected
    here. The host permission gate (``WidgetAccessMixin`` -> ``manifest_test_func``)
    runs in ``dispatch``; the shell renders the per-address disclosure and the
    non-secret router config. Executable swapping additionally requires that a
    viewed address is linked to the user and is the wallet's active account -- a
    visibility hint, with the live signature as the non-custodial guarantee.

    :var template_name: relative path to the Django template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "folks/index.html"
    manifest = MANIFEST
    bundle = None
    addresses = None

    def get_context_data(self, *args, **kwargs):
        """Expose bundle, addresses, the user-linked subset and router config.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["bundle"] = self.bundle
        context["addresses"] = self.addresses
        linked = linked_addresses_for_user(self.request.user, self.addresses.split(" "))
        context["linked_addresses"] = sorted(linked)
        context["router_id"] = self.manifest.id
        context["folks_network"] = getattr(settings, "FOLKS_NETWORK", "mainnet")
        context["folks_referrer"] = getattr(settings, "FOLKS_REFERRER_ADDRESS", "")
        context["folks_fee_bps"] = getattr(settings, "FOLKS_FEE_BPS", 0)
        return context

    def test_func(self):
        """Resolve bundle/addresses from the URL and apply the permission gate.

        :return: Boolean
        """
        url_path = self.args[0].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return self.manifest_test_func(len(self.addresses.split(" ")))
