"""Module containing Folks smart router widget's views."""

from api.client import engine_request
from api.widgets import bundle_and_addresses_from_path
from django.conf import settings
from django.views.generic.base import TemplateView
from walletauth.gating import is_linked_to_user, linked_addresses_for_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST

# Generic, data-named engine endpoints (shared by every router widget).
HOLDINGS_PATH = "/api/v2/internal/accounts/%s/holdings/"
ASSETS_PATH = "/api/v2/internal/assets/"


class FolksSwapView(WidgetAccessMixin, TemplateView):
    """Render the Folks swap widget shell for an address or bundle page.

    Engine-backed: holdings and asset metadata are fetched on demand by the htmx
    partial views below (via ``engine_request``), not injected here. The host
    permission gate (``WidgetAccessMixin`` -> ``manifest_test_func``) runs in
    ``dispatch``; the shell renders the per-address disclosure and the non-secret
    router config. Executable swapping additionally requires that a viewed address
    is linked to the user and is the wallet's active account -- a visibility hint,
    with the live signature as the non-custodial guarantee.

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
        linked = linked_addresses_for_user(
            self.request.user, self.addresses.split(" ")
        )
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


class FolksHoldingsView(WidgetAccessMixin, TemplateView):
    """htmx partial: fresh holdings for one linked address via ``account:holdings``.

    Gated to the user's own (linked) address so the engine call is both bounded
    and meaningful -- you only swap from an address you control. Renders the swap
    panel plus a JSON data island the controller reads for the SDK.

    :var template_name: relative path to the partial template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var address: the linked Algorand address whose holdings are fetched
    :type address: str
    """

    template_name = "folks/_panel.html"
    manifest = MANIFEST
    address = None

    def get_context_data(self, *args, **kwargs):
        """Fetch the address' holdings via the generic account:holdings endpoint.

        :var response: engine response carrying the holdings payload
        :type response: :class:`requests.Response`
        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        response = engine_request(
            "account:holdings",
            "GET",
            HOLDINGS_PATH % self.address,
            self.manifest.engine_endpoints,
        )
        context["address"] = self.address
        context["holdings"] = response.json().get("holdings", [])
        context["router_id"] = self.manifest.id
        return context

    def test_func(self):
        """Resolve the address and gate on permission plus user-linkage.

        :return: Boolean
        """
        self.address = self.args[0].upper()
        return self.manifest_test_func(1) and is_linked_to_user(
            self.request.user, self.address
        )


class FolksAssetsView(WidgetAccessMixin, TemplateView):
    """htmx partial: ranked asset metadata for a query via ``assets:lookup``.

    Used by the target-asset search box. Asset metadata is public, so this only
    requires an authenticated profile; an empty query skips the engine call.

    :var template_name: relative path to the partial template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    template_name = "folks/_assets.html"
    manifest = MANIFEST

    def get_context_data(self, *args, **kwargs):
        """Look up assets by name/unit/id for the ``q`` query parameter.

        :var query: trimmed search query from the request
        :type query: str
        :var response: engine response carrying the matched assets
        :type response: :class:`requests.Response`
        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        query = self.request.GET.get("q", "").strip()
        context["query"] = query
        context["assets"] = []
        if query:
            response = engine_request(
                "assets:lookup",
                "GET",
                ASSETS_PATH,
                self.manifest.engine_endpoints,
                params={"q": query},
            )
            context["assets"] = response.json().get("assets", [])
        return context

    def test_func(self):
        """Gate on an authenticated profile (asset metadata is public).

        :return: Boolean
        """
        return self.manifest_test_func(1)
