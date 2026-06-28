"""Shared, router-agnostic engine-data views for the swap feature.

Both swap-router widgets fetch the same data -- a linked address' fresh holdings
(``account:holdings``) and ranked asset metadata for the target search
(``assets:lookup``) -- so those two htmx partials live here once instead of being
re-declared by every router. The router-specific shell page stays in each router
widget; only this generic data is consolidated.
"""

import json

from api.client import fetch_account_holdings, fetch_asset_matches
from django.views.generic.base import TemplateView
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST


class SwapHoldingsView(WidgetAccessMixin, TemplateView):
    """htmx partial: fresh holdings for one linked address via ``account:holdings``.

    Gated to the user's own (linked) address so the engine call is both bounded
    and meaningful -- you only swap from an address you control. The backend
    returns ``{asset_id: {name, unit, decimals, amount}}``; this flattens it to a
    list (ALGO/id 0 first) for the shared panel template and emits a JSON island
    the controller reads for the SDK. Every returned asset is, by being present,
    opted in -- the controller derives opt-in from membership.

    :var template_name: relative path to the shared panel partial
    :type template_name: str
    :var manifest: the shared swap-core manifest (engine scopes + gate)
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var address: the linked Algorand address whose holdings are fetched
    :type address: str
    """

    template_name = "swap/_panel.html"
    manifest = MANIFEST
    address = None

    def get_context_data(self, *args, **kwargs):
        """Fetch and flatten the address' holdings for the panel.

        :var data: backend holdings mapping keyed by asset id
        :type data: dict
        :var holdings: flattened, id-sorted holdings list
        :type holdings: list
        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        data = fetch_account_holdings(self.address, self.manifest.engine_endpoints)
        holdings = [
            dict(meta, id=int(asset_id))
            for asset_id, meta in sorted(data.items(), key=lambda kv: int(kv[0]))
        ]
        context["address"] = self.address
        context["holdings"] = holdings
        context["holdings_json"] = json.dumps(holdings)
        return context

    def test_func(self):
        """Resolve the address and gate on permission plus user-linkage.

        :return: Boolean
        """
        self.address = self.args[0].upper()
        return self.manifest_test_func(1) and is_linked_to_user(
            self.request.user, self.address
        )


class SwapAssetsView(WidgetAccessMixin, TemplateView):
    """htmx partial: ranked asset metadata for a query via ``assets:lookup``.

    Used by the target-asset search box. Asset metadata is public, so this only
    requires an authenticated profile; an empty query skips the engine call.

    :var template_name: relative path to the shared assets partial
    :type template_name: str
    :var manifest: the shared swap-core manifest (engine scopes + gate)
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    template_name = "swap/_assets.html"
    manifest = MANIFEST

    def get_context_data(self, *args, **kwargs):
        """Look up assets by name/unit/id for the ``q`` query parameter.

        :var query: trimmed search query from the request
        :type query: str
        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        query = self.request.GET.get("q", "").strip()
        context["query"] = query
        context["assets"] = (
            fetch_asset_matches(query, self.manifest.engine_endpoints)
            if query
            else []
        )
        return context

    def test_func(self):
        """Gate on an authenticated profile (asset metadata is public).

        :return: Boolean
        """
        return self.manifest_test_func(1)
