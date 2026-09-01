"""Module containing Dust Sweep widget's views.

Two views: the shell page, and the one JSON endpoint the controller calls.

**One endpoint, because a sweep is a loop rather than a form.** The controller
asks what to sign next, the user signs it, and the controller asks again against
whatever the chain now says. There is no plan to store and nothing to resume:
"what should happen next" is a question about current state, so it is a question
the engine answers fresh every time.

That also removes the two things a multi-step flow would have needed. There is
no server-side session to keep, so it does not matter which worker takes the
next request; and there is no batch signing to build, because the wallet bridge
already signs exactly one group per call.

The router-agnostic partials (fresh holdings, asset search) are *not* here. They
are shared and live in :mod:`widgets.inhouse.swapcore.views`.
"""

import json

from api.client import BackendError, engine_request
from django.conf import settings
from api.widgets import bundle_and_addresses_from_path
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView, View
from walletauth.gating import is_linked_to_user, linked_addresses_for_user
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST

#: Engine path behind the sweep scope. Absolute from the API root: `_request`
#: concatenates it onto the host, and a relative path silently produced
#: `http://host:8001router/sweep/`, which reaches nothing.
SWEEP_PATH = "/api/v2/internal/router/sweep/"

#: Router application the browser requires a conversion group to actually call.
#:
#: The controller refuses a group labelled ``convert`` that calls no guarded
#: router method, because the contract's own checks - the hygiene guard, the
#: input proven spent, the co-signed floor - run only when the router is in the
#: group. That is the audit's ``S7``.
#:
#: **It is handed down from here rather than read from the plan.** The plan
#: response is the thing the check exists to doubt; an application id taken from
#: it would make the rule agree with whatever the engine wanted. ``dustsweep.js``
#: carries the same number as a fallback, so a missing setting cannot disable
#: the rule - this exists so a redeployment can be followed without a widget
#: release.
ROUTER_APP_ID = 3689591968


class DustSweepView(WidgetAccessMixin, TemplateView):
    """Render the Dust Sweep shell for an address or bundle page.

    :var template_name: relative path to the Django template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "dustsweep/index.html"
    manifest = MANIFEST
    bundle = None
    addresses = None

    def get_context_data(self, *args, **kwargs):
        """Expose bundle, addresses and the user-linked subset.

        Only linked addresses can be swept, so the template renders a panel per
        linked address and nothing at all for the rest.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["bundle"] = self.bundle
        context["addresses"] = self.addresses
        linked = linked_addresses_for_user(self.request.user, self.addresses.split(" "))
        context["linked_addresses"] = sorted(linked)
        context["widget_id"] = self.manifest.id
        context["router_app_id"] = getattr(settings, "ROUTER_APP_ID", ROUTER_APP_ID)
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


@method_decorator(never_cache, name="dispatch")
class DustSweepPlanView(WidgetAccessMixin, View):
    """JSON endpoint: what the sweep asks this address to sign next.

    **Never cached.** The answer is a statement about the account's holdings and
    the pools' reserves at a moment, and it carries a transaction group built
    against a specific round. Serving a stale one would hand a user a group the
    chain no longer accepts - or, worse, a forfeit priced before the token moved.

    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var address: the linked address being swept
    :type address: str
    """

    manifest = MANIFEST
    address = None

    def post(self, request, *args, **kwargs):
        """Forward the request to the engine and return its answer.

        :return: :class:`django.http.JsonResponse`
        """
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "malformed request"}, status=400)

        if not isinstance(payload, dict):
            return JsonResponse({"error": "malformed request"}, status=400)

        # the address is the gated one rather than whatever the body claims, so
        # a tampered body cannot plan a sweep of somebody else's account
        payload["address"] = self.address
        try:
            answered = engine_request(
                "router:sweep",
                "POST",
                SWEEP_PATH,
                self.manifest.engine_endpoints,
                json=payload,
            ).json()
        except BackendError as error:
            return JsonResponse(
                {"error": error.detail or "the sweep is unavailable"},
                status=error.status_code or 502,
            )

        return JsonResponse(answered)

    def test_func(self):
        """Gate on permission plus the address being the user's own.

        Held to the same bar as the swap endpoints, and for a stronger reason:
        this one reads an entire account and returns transactions that close its
        holdings out. Planning a sweep for an address you do not control would
        disclose the whole portfolio and hand back a group to empty it.

        :return: Boolean
        """
        self.address = self.request.GET.get("address", "").strip().upper()
        if not self.address:
            return False

        return self.manifest_test_func(1) and is_linked_to_user(
            self.request.user, self.address
        )
