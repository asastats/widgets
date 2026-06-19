"""Module containing Folks smart router widget's views."""

import json

from api.widgets import bundle_and_addresses_from_path
from django.conf import settings
from django.views.generic.base import TemplateView
from walletauth.gating import linked_addresses_for_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST


class FolksSwapView(WidgetAccessMixin, TemplateView):
    """Render the Folks swap widget shell for an address or bundle page.

    Public-capability widget: no ``engine_request`` calls. The host permission
    gate (``WidgetAccessMixin`` -> ``manifest_test_func``) runs in ``dispatch``.

    Executable swapping additionally requires that an address being viewed is
    linked to the current user. That subset comes from
    ``walletauth.gating.linked_addresses_for_user`` (the host's self-scoped
    "is this address connected to me?" check) and is surfaced to the browser,
    which intersects it with the wallet's active account. Per walletauth's own
    design this is a visibility hint, not the authorization -- the live wallet
    signature over the atomic group is the real, non-custodial guarantee.

    The fee/referrer/network values are non-secret deployment config (a /pro API
    key, if ever used, must stay server-side and proxy the SDK instead).

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
        # walletauth:linked_addresses — subset of the page's addresses connected
        # to the current user (space-joined for the template).
        linked = linked_addresses_for_user(
            self.request.user, self.addresses.split(" ")
        )
        context["linked_addresses"] = " ".join(sorted(linked))
        context["router_id"] = self.manifest.id
        # portfolio:asas — per-address ASA holdings for the linked addresses,
        # injected server-side because the public /api/v2 API is JWT-only and the
        # browser only has the session. Shape consumed by folks.js:
        #   { "<ADDRESS>": [ {"id": int, "unit": str, "decimals": int,
        #                      "amount": int}, ... ], ... }
        # (flattened from AsaItemSerializer: asset.{id,unit,decimals} + amount).
        # TODO(host-seam): resolve each linked address's ASA items via the host's
        # account-serialization path. Confirm whether that path is engine-backed;
        # if so, the holdings are still injected by the host (which has engine
        # access) so this widget itself stays `public`.
        context["holdings_json"] = json.dumps(
            {address: [] for address in sorted(linked)}
        )
        # Non-secret deployment config consumed by folks.js.
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
