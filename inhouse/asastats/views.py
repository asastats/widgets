"""Module containing ASA Stats smart router widget's views.

Three views: the shell page, and the two JSON endpoints the browser adapter
calls for a quote and for the group that executes it.

**Why this router needs endpoints of its own.** Folks and Haystack quote in the
browser against their vendors' APIs, so their widgets ship an SDK bundle and no
server-side swap code at all. Ours cannot: the routing *is* ours, and it runs in
the engine - the pair graph, the live pool reads, the allocator and the two-leg
route collapse. So the browser asks us, and these proxy to the engine under the
scopes the manifest declares. Nothing about a quote is computed client-side,
which also means no quote parameter a user could tamper with reaches a pool
without passing the engine first.

The router-agnostic partials (fresh holdings, asset search) are *not* here.
They are shared and live in :mod:`widgets.inhouse.swapcore.views`, mounted once
for every router.
"""

import json

from api.client import engine_request
from api.widgets import bundle_and_addresses_from_path
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView, View
from walletauth.gating import is_linked_to_user, linked_addresses_for_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST

#: Engine paths behind the two router scopes.
QUOTE_PATH = "router/quote/"
GROUP_PATH = "router/group/"


class AsastatsSwapView(WidgetAccessMixin, TemplateView):
    """Render the ASA Stats smart router shell for an address or bundle page.

    Mirrors :class:`widgets.inhouse.folks.views.FolksSwapView`, minus the
    vendor configuration: there is no API key, no network toggle and no
    referrer address to hand the browser, because the browser never talks to a
    router. The only configuration it needs is which router it is.

    :var template_name: relative path to the Django template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "asastats/index.html"
    manifest = MANIFEST
    bundle = None
    addresses = None

    def get_context_data(self, *args, **kwargs):
        """Expose bundle, addresses and the user-linked subset.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["bundle"] = self.bundle
        context["addresses"] = self.addresses
        linked = linked_addresses_for_user(self.request.user, self.addresses.split(" "))
        context["linked_addresses"] = sorted(linked)
        context["router_id"] = self.manifest.id
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


class _RouterEndpoint(WidgetAccessMixin, View):
    """Shared behaviour for the two JSON endpoints the adapter calls.

    Both take the same body, both are gated the same way, and both do nothing
    with the payload but hand it to the engine. Keeping that in one place is
    what stops the gate from being applied to one and forgotten on the other.

    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var scope: engine scope this endpoint calls under
    :type scope: str
    :var path: engine path beneath the API root
    :type path: str
    :var address: the linked address the swap is for
    :type address: str
    """

    manifest = MANIFEST
    scope = None
    path = None
    address = None

    def post(self, request, *args, **kwargs):
        """Forward the request body to the engine and return its answer.

        :return: :class:`django.http.JsonResponse`
        """
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "malformed request"}, status=400)

        if not isinstance(payload, dict):
            return JsonResponse({"error": "malformed request"}, status=400)

        # the address is the gated one rather than whatever the body claims,
        # so a tampered body cannot quote or build for somebody else
        payload["address"] = self.address
        return JsonResponse(
            engine_request(
                self.scope,
                "POST",
                self.path,
                self.manifest.engine_endpoints,
                json=payload,
            )
        )

    def test_func(self):
        """Gate on permission plus the address being the user's own.

        A quote is harmless, but the group this builds spends the address'
        assets, so both endpoints are held to the same bar as the holdings
        partial: you may only route from an address you have linked.

        :return: Boolean
        """
        self.address = self.request.GET.get("address", "").strip().upper()
        if not self.address:
            return False

        return self.manifest_test_func(1) and is_linked_to_user(
            self.request.user, self.address
        )


@method_decorator(never_cache, name="dispatch")
class AsastatsQuoteView(_RouterEndpoint):
    """JSON endpoint: quote a swap through the ASA Stats smart router.

    Never cached. A quote is a statement about pool reserves at a moment, and a
    stale one produces a `minimum_received` the chain will not honour - the
    group is then rejected rather than settled badly, but the caller has still
    signed for nothing.
    """

    scope = "router:quote"
    path = QUOTE_PATH


@method_decorator(never_cache, name="dispatch")
class AsastatsGroupView(_RouterEndpoint):
    """JSON endpoint: build the transaction group a quote implies.

    Returns the group unsigned, for the wallet to sign - the ASA Stats router's
    groups are all user-signed, so the adapter can use `buildSwapGroup` rather
    than owning execution the way Haystack must.

    **One case is refused rather than mis-built.** A Tinyman v1 leg is paid out
    by the pool's own logic signature, so a group containing one is not
    all-user-signed and cannot be handed whole to the wallet. The engine
    excludes v1 from anything it builds for this path; see runbook.rst.
    """

    scope = "router:group"
    path = GROUP_PATH
