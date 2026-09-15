"""Module containing Real-time refresh widget's views.

**A widget with almost no code, and deliberately so.** The work happens in the
engine: its live pass re-prices a page on every block and publishes the result
to this deployment's own Redis. This reads that, and tells the engine somebody
is still looking.

It is a widget rather than a feature of the address page because it is a thing a
reader *selects* and a subscriber *pays for*, and because a fork of this site
should be able to host it for its own users on its own terms - which means a
manifest with permission bands, like the historic widget, rather than a
condition written into a view.

**Nothing is called on the reader's behalf**, so the manifest declares no engine
scopes. A deployment that cannot reach the engine's HTTP API can still serve
this, as long as its engine runs the pass.
"""

import time

from api.widgets import bundle_and_addresses_from_path
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView
from utils.clients import redis_instance
from widgethost.enforcement import WidgetAccessMixin

from .manifest import MANIFEST

#: Sorted set the engine's live pass reads to decide which pages to re-price.
#: Members are space-joined address strings, scored by the unix time this view
#: last served a poll for them. See the engine's `CACHE_KEY_LIVE_SUBSCRIBED`.
SUBSCRIBED_KEY = "lvx"
#: Prefix the pass publishes under, keyed by bundle. See `CACHE_KEY_LIVE_PAYLOAD`.
PAYLOAD_PREFIX = "lvp"


@method_decorator(never_cache, name="dispatch")
class LiveRefreshView(WidgetAccessMixin, TemplateView):
    """GET /widgets/liverefresh/<value> -> the fragments this block changed.

    **The poll is the heartbeat.** Serving it is what tells the engine the page
    is being read, so there is no subscribe and no unsubscribe to keep in step
    with a reader who closed the tab: they simply stop polling and the page ages
    out of the set. That is also why this is a poll at all - a websocket would
    need a consumer, a channel layer and a Daphne, to carry a payload that is
    already sitting in Redis where a plain view can read it.

    :var template_name: relative path to the Django template
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "liverefresh/fragments.html"
    manifest = MANIFEST
    bundle = None
    addresses = None

    def get(self, request, *args, **kwargs):
        """Return the changed fragments, or 204 when nothing moved.

        **204 rather than an empty body**: htmx leaves the page alone on a 204,
        so a block that moved nothing costs one request and no DOM work, which
        is most blocks for most pages.

        :return: :class:`HttpResponse`
        """
        client = redis_instance()
        self._heartbeat(client)

        payload = self._payload(client)
        if payload is None:
            # Nothing published: the pass has not reached this page yet, or the
            # reader has only just asked for it. Leave the page as it is.
            return HttpResponse(status=204)

        if payload.get("total") == self._last_total():
            return HttpResponse(status=204)

        self.request.session[self._session_key()] = payload.get("total")
        context = self.get_context_data(payload=payload, **kwargs)
        return self.render_to_response(context)

    def _heartbeat(self, client):
        """Say the page is being read, so the engine keeps re-pricing it."""
        client.zadd(SUBSCRIBED_KEY, {self.addresses: time.time()})

    def _payload(self, client):
        """Return what the pass last published for this page, or None."""
        import msgpack

        raw = client.get(f"{PAYLOAD_PREFIX}:{self.bundle}")
        if not raw:
            return None
        # `strict_map_key=False` because the values map is keyed by asset id,
        # and msgpack refuses integer keys by default.
        payload = msgpack.unpackb(raw, strict_map_key=False)

        # **Derived when the engine did not send it**, which is any block
        # published by an engine older than the one that added the field. The
        # two services deploy separately, so that window is real rather than
        # hypothetical - and the band reads every figure it shows off this
        # payload, so a missing key is a figure the reader watches go blank.
        if not payload.get("pricealgo") and payload.get("priceusdc"):
            payload["pricealgo"] = 1 / payload["priceusdc"]
        return payload

    def _session_key(self):
        return f"liverefresh:{self.bundle}"

    def _last_total(self):
        """Return the total this reader was last shown, or None."""
        return self.request.session.get(self._session_key())

    def get_context_data(self, *args, **kwargs):
        """Expose the published payload to the fragment template.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["addresses"] = self.addresses
        context["bundle"] = self.bundle
        return context

    def test_func(self):
        """Resolve the page from the URL and apply the manifest gate.

        :return: Boolean
        """
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            self.kwargs.get("value") or self.args[0]
        )
        return self.manifest_test_func(len(self.addresses.split()))
