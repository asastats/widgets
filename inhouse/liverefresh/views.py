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

import json
import time

from api.widgets import bundle_and_addresses_from_path
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView
from utils.clients import redis_instance
from utils.layouts import layout_for_user
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin

from .allowance import left, requires_linked_address, spend
from .manifest import MANIFEST

#: Sorted set the engine's live pass reads to decide which pages to re-price.
#: Members are space-joined address strings, scored by the unix time this view
#: last served a poll for them. See the engine's `CACHE_KEY_LIVE_SUBSCRIBED`.
SUBSCRIBED_KEY = "lvx"
#: Sorted set of pages a *paying* reader has open, scored the same way. The
#: engine keeps these ahead of the rest when the block budget runs out, so a
#: free reader's page is shed before a subscriber's. See `CACHE_KEY_LIVE_PAID`.
PAID_KEY = "lvq"
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
        # One timestamp for one poll. Read twice, the heartbeat and the paid
        # mark carry different scores for the same event, and the two sets age
        # out of step - by microseconds, but for no reason at all.
        now = time.time()
        self._heartbeat(client, now)

        # **Read first, charge later.** What is left decides two things that
        # must be answered before the payload is looked at - whether this reader
        # is paying, and whether they have run out - and neither of them may
        # cost the reader time. `left` spends nothing.
        remaining_seconds = self._left(client)
        if remaining_seconds is None:
            # **No daily limit means this reader is paying for it**, and the
            # engine needs to know before capacity runs out rather than after.
            # Same score and the same 90-second ageing as `lvx`, so a page stops
            # counting as paid 90 s after the last subscriber closes it and
            # nothing has to expire it on purpose.
            #
            # **Marked before the payload is looked at, deliberately.** This is
            # what lifts a page over the admission budget, and a page that is
            # not admitted is never published - so deciding it on whether
            # something has been published would make a shed page's shedding
            # permanent.
            client.zadd(PAID_KEY, {self.addresses: now})
        elif remaining_seconds <= 0:
            # Told before the payload is read, and not folded into the "nothing
            # published" branch below: a reader who is out must be *told* so the
            # widget stops polling and `address.js` takes the plain reload back
            # up. Answering them with a 204 would leave them with neither.
            return self._spent_response()

        payload = self._payload(client)
        if payload is None:
            # **Nothing published, so nothing is charged.**
            #
            # The pass has not reached this page yet, the reader has only just
            # asked for it, or - the case that made this a bug rather than an
            # edge - the page was shed by admission control and its payload
            # aged out of the 120 s TTL behind it. On 2026-09-16 the overnight
            # rotation shed 528 of 978 wanted pages at once, and every reader of
            # one of those was being billed wall-clock seconds for a page that
            # could not move.
            #
            # A deployment whose engine publishes nothing at all is the same
            # shape: a fork can host this widget - it reads its own Redis and
            # spends none of our API - but with no live pass behind it the
            # payload never arrives, and charging an allowance down to zero for
            # a feature that never produced a figure is indefensible.
            #
            # `left` reads the balance without spending, so the badge still
            # shows the truth while the reader waits.
            return self._with_left(HttpResponse(status=204), remaining_seconds)

        # Delivered, so charged. This is the only call that spends.
        remaining_seconds = self._allowance(client, now)
        if remaining_seconds is not None and remaining_seconds <= 0:
            return self._spent_response()

        reload = self._reload_response(request, payload)
        if reload is not None:
            return self._with_left(reload, remaining_seconds)

        if payload.get("total") == self._last_total():
            return self._with_left(HttpResponse(status=204), remaining_seconds)

        self.request.session[self._session_key()] = payload.get("total")
        context = self.get_context_data(payload=payload, **kwargs)
        return self._with_left(self.render_to_response(context), remaining_seconds)

    @staticmethod
    def _with_left(response, seconds):
        """Attach what is left of the allowance to a response, for the badge.

        **On every response, including the 204s.** Most blocks move nothing, so
        a figure sent only with changed fragments would sit still for minutes on
        a quiet page and then jump - which reads as broken rather than as quiet.
        htmx processes `HX-Trigger` on a 204 as readily as on a body.

        Nothing is attached for the unmetered tiers: there is no number to show,
        and a header saying so would invite the script to render a zero.

        :param response: the response this poll is about to return
        :type response: :class:`HttpResponse`
        :param seconds: allowance left, or None when unlimited
        :type seconds: float or None
        :return: :class:`HttpResponse`
        """
        if seconds is None:
            return response
        response["HX-Trigger"] = json.dumps(
            {"liverefresh:left": {"seconds": int(max(0, seconds))}}
        )
        return response

    def _permission(self):
        """Return the reader's permission integer, or 0 when they have none.

        :return: int
        """
        profile = getattr(self.request.user, "profile", None)
        return getattr(profile, "permission", 0) or 0

    def _left(self, client):
        """Return what is left without spending any, or None for unlimited.

        :param client: Redis client instance
        :type client: :class:`Redis`
        :return: float or None
        """
        return left(
            self._permission(),
            self.addresses.split()[0],
            self.request.user.pk,
            client,
        )

    def _allowance(self, client, now):
        """Charge this poll and return what is left, or None for unlimited.

        None means unlimited, which is every tier from Asastatser up and costs
        no round trip. Everyone else is buying a look at what they would get.

        **The free tier spends an address's bucket, not a reader's day.** An
        allowance bound to an account is bound to the cheapest thing in the
        system, so it is bound to the address instead - see `allowance`. Intro
        keeps the daily per-reader clock, because a paying reader is not what
        the anti-abuse design is defending against.

        :param client: Redis client instance
        :type client: :class:`Redis`
        :return: float or None
        """
        profile = getattr(self.request.user, "profile", None)
        permission = getattr(profile, "permission", 0) or 0
        # The metered bands are one address wide (`max_addresses = 1` in the
        # manifest), so the page and the address are the same thing here; the
        # unmetered ones never reach the address at all.
        return spend(
            permission,
            self.addresses.split()[0],
            self.request.user.pk,
            client,
            now,
        )

    def _spent_response(self):
        """Tell the page the day's free watching is used up.

        **Not a 204.** A reader whose page simply stopped moving would have no
        way to tell that from the feature being broken, and would be left with
        neither the live updates nor the 60-second reload that non-subscribers
        get - strictly worse than never having had it. `HX-Trigger` fires a DOM
        event the widget's script listens for: it stops polling, reveals the
        notice, and takes the marker off the page, which is what lets
        `address.js` pick the plain reload back up.

        :return: :class:`HttpResponse`
        """
        response = HttpResponse(status=200)
        response["HX-Trigger"] = "liverefresh:spent"
        return response

    def _reload_response(self, request, payload):
        """Return a reload instruction when the *holdings* changed, else None.

        **The fragments cannot express this, and that is not a gap that can be
        closed by sending more of them.** An out-of-band swap needs an element
        on the reader's page to land in, so an asset just bought has no row to
        arrive in, one just sold is never mentioned and its row stays exactly as
        it was, and the amount column is not what a value fragment carries. What
        the engine publishes can only ever move figures that are already there.

        So when the holdings themselves move, the honest update is the page: it
        is the one renderer that produces rows, and reusing it is what keeps
        this from growing a second one that would drift. It is also rare - a
        page reloads when its account transacts, not when a price moves - which
        is why the fingerprint is over amounts and never over values.

        ``HX-Refresh`` rather than anything of our own: htmx reloads on it, and
        the address page's cache entry is keyed on the same fingerprint, so the
        reload cannot be answered with the markup that prompted it.

        Sent by the page rather than remembered per reader, because a session
        would record the fingerprint at the *first poll* - and a change between
        the render and that poll would then never be noticed at all. What the
        reader is looking at is what has to be compared.

        No parameter means a page that predates this, or the legacy layout;
        an empty published fingerprint means an engine that predates it. Both
        degrade to what happened before, which is fragments only.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :param payload: what the pass last published for this page
        :type payload: dict
        :return: :class:`HttpResponse` or None
        """
        rendered = request.GET.get("holdings")
        published = payload.get("holdings")
        if not rendered or not published or rendered == published:
            return None

        response = HttpResponse(status=200)
        response["HX-Refresh"] = "true"
        return response

    def _heartbeat(self, client, now):
        """Say the page is being read, so the engine keeps re-pricing it."""
        client.zadd(SUBSCRIBED_KEY, {self.addresses: now})

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
        # **The same helper the address page keys its cache entry on.** The
        # fragments address ids only one layout renders, so serving the wrong
        # set means every swap lands nowhere - and htmx says so, loudly, on
        # every poll. Deriving it here rather than trusting a parameter keeps
        # the two from ever disagreeing about which markup this reader holds.
        context["layout"] = layout_for_user(getattr(self.request, "user", None))
        return context

    def test_func(self):
        """Resolve the page from the URL and apply the manifest gate.

        :return: Boolean
        """
        # **`force_bundle=False`, because the engine does not hash a single
        # address.** Its pass publishes under
        # `bundle_from_addresses(addresses) if " " in addresses else addresses`
        # - the raw address when there is only one, the hash when there are
        # several. Hashing unconditionally here asked for a key nothing writes.
        #
        # The failure had the worst possible shape: the poll still ran, still
        # heartbeated, so the engine went on re-pricing the page every block -
        # and every response was a 204, so the reader saw a live indicator over
        # a page that never moved and nothing anywhere logged a problem. A
        # bundle worked throughout, because both sides hash those.
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            self.kwargs.get("value") or self.args[0], force_bundle=False
        )
        if not self.manifest_test_func(len(self.addresses.split())):
            return False

        # **The free tier may only watch an address it has connected.**
        #
        # The free allowance is spent per address so that farming accounts buys
        # nothing, and this is the other half of that: without it, an abuser
        # needs no accounts at all, only a list of other people's addresses, and
        # every one of them arrives with a fresh two hours. Requiring the wallet
        # signature means the addresses a reader can spend are the addresses
        # they control, and those are the ones already holding their portfolio.
        #
        # Self-scoped by `linked_addresses_for_user`, which only ever reads the
        # requesting user's own rows - never an oracle for whose address this
        # is. Paid tiers are unaffected: watching an address you do not own is
        # a perfectly ordinary thing to buy.
        profile = getattr(self.request.user, "profile", None)
        if requires_linked_address(getattr(profile, "permission", 0) or 0):
            return all(
                is_linked_to_user(self.request.user, address)
                for address in self.addresses.split()
            )
        return True
