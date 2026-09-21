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
from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS as MAX_FRAGMENTS
from utils.constants.core import (
    LIVEREFRESH_RELOAD_COOLDOWN_SECONDS as RELOAD_COOLDOWN,
)
from utils.layouts import layout_for_user
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin

from . import warmset
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


def _asset_key(key):
    """Return `key` as the asset id it was before a session stringified it.

    Anything that is not a plain asset id is handed back untouched rather than
    forced, so a future payload keyed by something else survives the trip
    instead of raising on the way out.

    :param key: a mapping key read back from the session
    :return: int or the original key
    """
    try:
        return int(key)
    except (TypeError, ValueError):
        return key


def _bundle(held):
    """Return one asset's share of a payload, in the shape the carry stores.

    **Tolerant of the shape this replaced**, because a reader mid-resync when
    the code changes has a session holding the old one: until 2026-09-21 the
    carry was `{asset id: value}` and nothing else, so a bare number here is a
    value with no amount and no positions rather than a corrupt entry. Treating
    it as one would strand that reader's backlog until their session expired.

    :param held: a carried bundle, a bare carried value, or None for a new one
    :type held: dict or float or None
    :return: dict
    """
    if isinstance(held, dict):
        return {
            "value": held.get("value"),
            "amount": held.get("amount"),
            "positions": list(held.get("positions") or ()),
        }
    return {"value": held, "amount": None, "positions": []}


def _fragments(bundles):
    """Return how many out-of-band elements `bundles` would put on the wire.

    The unit the budget is spent in, and it counts elements rather than assets
    because that is what the browser pays for: htmx locates each by id and
    replaces it, and every replacement invalidates layout.

    A position costs two when it carries an amount and one when it does not,
    matching the template - `positionvalue` always, `positionamount` only
    `{% if position.amount %}`.

    :param bundles: {asset key: bundle}, as `_bundle` shapes them
    :type bundles: dict
    :return: int
    """
    total = 0
    for held in bundles.values():
        total += held.get("value") is not None
        total += held.get("amount") is not None
        for position in held.get("positions") or ():
            total += 2 if position.get("amount") else 1
    return total


def _rebuilt(payload, bundles):
    """Return `payload` carrying only what `bundles` holds.

    The inverse of the split: the fragment template reads `payload.values`,
    `payload.amounts` and `positions`, so the per-asset grouping the budget is
    spent in has to be taken apart again before it is rendered.

    :param payload: what the pass published, as `_payload` decoded it
    :type payload: dict
    :param bundles: {asset key: bundle} to send
    :type bundles: dict
    :return: dict
    """
    return dict(
        payload,
        values={
            key: held["value"]
            for key, held in bundles.items()
            if held.get("value") is not None
        },
        amounts={
            key: held["amount"]
            for key, held in bundles.items()
            if held.get("amount") is not None
        },
        positions=[
            position
            for held in bundles.values()
            for position in held.get("positions") or ()
        ],
    )


def _named_positions(payload):
    """Return the published positions, each carrying the id its row was given.

    **The engine cannot name a position and the page cannot value one.** A
    position's `pid` is the website's identifier, built from what the position
    is (`api/position_id.py`), and the live pass never serializes a position so
    it cannot build one. It sends the identifying fields instead and this joins
    the two.

    Which linked entries identify rather than describe is decided here too, by
    `identifying_link_ids` - so the engine ships every link with its text and
    the rule stays in one place.

    A position the engine dropped as indistinguishable never arrives, and one
    whose row the page left unnamed has no element to land on. Both are
    corrected by the reload, as they always were.

    :param payload: what the pass published, as `_payload` decoded it
    :type payload: dict
    :return: list
    """
    from api.position_id import identifying_link_ids, position_id_from_fields

    named = []
    for position in (payload or {}).get("positions") or ():
        asset_id = position.get("asset")
        if asset_id is None:
            continue
        named.append(
            dict(
                position,
                pid=position_id_from_fields(
                    asset_id,
                    position.get("fields") or {},
                    identifying_link_ids(position.get("links")),
                ),
            )
        )
    return named


def _digest(fingerprint):
    """Return the part of `fingerprint` that says *what* is held.

    `<counter>:<digest>` - the counter is how many times the account has been
    struck, the digest is over the asset id set. A fingerprint that predates the
    counter, or any shape without a separator, is returned whole: comparing it
    against itself still works, and guessing at it would not.

    :param fingerprint: what `_holdings_fingerprint` made
    :type fingerprint: str
    :return: str
    """
    return fingerprint.split(":", 1)[-1]


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
        warm = self._heartbeat(client, now)

        # **Read first, charge later.** What is left decides two things that
        # must be answered before the payload is looked at - whether this reader
        # is paying, and whether they have run out - and neither of them may
        # cost the reader time. `left` spends nothing.
        remaining_seconds = self._left(client)

        if not warm:
            # **Over this reader's warm-set cap**, so this page is not being
            # kept alive for them and cannot move. Charging for it would be the
            # same defect as billing a reader for a page admission control had
            # shed - see the branch below, which exists because that happened.
            #
            # Nor is it marked paid: `lvq` lifts a page over the engine's
            # admission budget, and asking the engine to prioritise a page we
            # have deliberately not subscribed would be asking for work we just
            # decided not to want.
            #
            # 204 rather than the spent response: they have not run out of
            # anything, and their other tabs are still live. The page simply
            # goes static, which is exactly what a shed page does.
            return self._with_left(HttpResponse(status=204), remaining_seconds)

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
            # The page is about to be re-rendered whole, so anything still
            # queued describes markup that will not exist in a moment.
            self.request.session.pop(self._carry_key(), None)
            return self._with_left(reload, remaining_seconds)

        payload, sending = self._chunked(payload)

        # **`sending` first**, because a resync can outlive the block that
        # started it: the total settles while values are still going out, and
        # answering 204 then would strand the rest of them.
        if not sending and payload.get("total") == self._last_total():
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

        # **Only the asset *set* needs the page rebuilt; the counter does not.**
        #
        # A fingerprint is `<counter>:<digest>`. The counter steps on every block
        # that strikes the account while the digest covers which assets are held,
        # so comparing whole fingerprints rebuilt a transacting account's page on
        # almost every block - costing the reader their scroll, their filters and
        # every section they had open - to correct figures the fragments carry.
        #
        # **This was tried on 2026-09-19 and reverted within the hour, and the
        # reason is the bar for putting it back.** Fragments reached a row's
        # aggregate and nothing inside it: a row's positions - "Wallet balance",
        # a farm, a lend - rendered with no id, so nothing addressed them and the
        # rebuild was the only thing that ever corrected one. Removing it froze
        # every position while the total above it stayed live, which is a page
        # disagreeing with itself about money. Observed as 1 USDC between two
        # watched pages: the sender's "Wallet balance" sat at 3.7552 until F5.
        #
        # What makes it safe now is that a position is addressable and published:
        # `pq-<pid>` and `pv-<pid>` on the page, `positions` in the payload, and
        # a handler that carries the new figure up to the `.position`'s own
        # `data-value` so the band keeps agreeing with its rows. Narrowing this
        # again without all three is how the same bug comes back.
        #
        # Two cases still rebuild, and both are right to. A genuinely new asset
        # has no row for a fragment to land in. A position the page could not
        # name - three on the reference bundle are indistinguishable - gets no
        # id and no fragment, so its figure waits for the next rebuild.
        if _digest(rendered) == _digest(published):
            return None

        # Refusing here rather than in the script: the reader's page has no way
        # to know how often it has been told to reload, and a client-side guard
        # would have to survive the very reloads it is counting.
        now = time.time()
        last = self.request.session.get(self._reload_key())

        # **A gap clears it, and that is what makes this a cooldown rather than
        # a deadline.** The stamp lives in the session, so it survived the tab
        # being closed: a reader who was told to reload, closed the window,
        # transacted and came back was refused the reload they now genuinely
        # needed, and sat on stale rows until the clock ran out. Reported
        # 2026-09-18 as "it took 60 seconds and an F5" - this constant, to the
        # second.
        #
        # Keying on the fingerprint instead does not work, and the loop above is
        # why: the counter steps on every block that strikes the account, so in
        # a runaway the fingerprint is *different* on every pass and a
        # fingerprint key would wave every reload through - which is the bug
        # this was written for.
        #
        # What separates the two cases is not what changed but how continuously.
        # A runaway is found out of date on essentially every poll, so this gap
        # never opens; a closed window is not polling at all, so it opens at
        # once. Recorded here rather than on every poll deliberately: the
        # question is when this reader was last *found stale*, and a page that
        # has been in sync for ten minutes has no cooldown worth keeping.
        stale = self.request.session.get(self._stale_key())
        if stale and now - stale > RELOAD_COOLDOWN:
            last = None
        self.request.session[self._stale_key()] = now

        if last and now - last < RELOAD_COOLDOWN:
            # Fragments still go out; the reader keeps getting live figures
            # while the row structure waits for the cooling-off to pass.
            return None
        self.request.session[self._reload_key()] = now

        response = HttpResponse(status=200)
        response["HX-Refresh"] = "true"
        return response

    def _heartbeat(self, client, now):
        """Say the page is being read, so the engine keeps re-pricing it.

        **Only if this reader's warm set has room for it.** The manifest's
        bands are checked per *page*, so a reader may hold several pages at
        once and clear every check - five tabs of five-address bundles pass
        five checks of five addresses each, and twenty-five addresses are
        re-priced every block.
        The warm set is what counts a reader's addresses across every tab and
        every surface; see `warmset`.

        **A page that does not fit is simply not warmed.** It is not refused
        and nothing is raised: the reader still gets whatever the pass has
        published for it, because reading a payload another reader caused to
        exist is free. What the cap bounds is the work a reader can *cause*,
        not the data they may see - which is also why this sits here rather
        than in the access check.

        :param client: Redis client instance
        :type client: :class:`Redis`
        :param now: unix time to score the touch with
        :type now: float
        :var admitted: the addresses this poll kept warm, empty when over cap
        :type admitted: list
        :return: bool
        """
        admitted, _ = warmset.touch(
            self.request.user.pk,
            self.addresses.split(),
            warmset.cap_for(self._permission(), self.manifest.required_permission),
            client,
            now,
        )
        if not admitted:
            return False
        client.zadd(SUBSCRIBED_KEY, {self.addresses: now})
        return True

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

    def _reload_key(self):
        """Key holding when this reader was last told to reload this page."""
        return f"liverefresh:reloaded:{self.bundle}"

    def _stale_key(self):
        """Key holding when this reader's page was last found out of date.

        Not "when they last polled": a page in sync polls without ever reaching
        the cooldown, and a cooldown it has outlived is not worth keeping. See
        `_reload_response` for what the gap between this and now decides.
        """
        return f"liverefresh:stale:{self.bundle}"

    def _carry_key(self):
        """Key holding the values this reader is still owed for this page."""
        return f"liverefresh:carry:{self.bundle}"

    def _chunked(self, payload):
        """Return `payload` trimmed to `MAX_FRAGMENTS` fragments, and whether any.

        **The engine sends everything after a re-read, and that is deliberate.**
        A reader polling every three seconds against blocks arriving every 2.7
        cannot see every diff, so the periodic full payload is what heals the
        drift. It cannot be turned into a diff without making values quietly
        wrong on every page, to fix one.

        What it can be is *spread*. One account measured 85 kB of fragments in a
        single response - ten times what the docstring on `_live_payload` calls
        a full one - which htmx then has to parse and out-of-band swap into a 22
        MB document, every time the account is struck. The reader's browser, not
        the engine, is what that overwhelms.

        So the payload is queued and released `MAX_FRAGMENTS` at a time. Nothing
        is dropped: what does not fit stays in the session and goes out on the
        polls that follow, newest figure winning if the same asset moves again
        mid-resync. A resync of nine hundred holdings finishes in about half a
        minute of polling instead of arriving as one unusable lump.

        **Only large payloads are touched.** An ordinary block's diff is a
        handful of figures and passes through whole, which is every page but
        this kind of one.

        **The budget is fragments, not assets, and that is the correction.**
        Until 2026-09-21 this counted `values` alone, because when it was
        written a changed asset *was* one fragment. `11f5e9f` then began
        publishing `positions` - the rows inside a row - and `amounts` beside
        them, and neither passed through here at all. A wide account's full
        payload went out as a hundred capped values plus every amount and every
        position uncapped: measured on production at 46.5 kB and on the order of
        a thousand out-of-band swaps, every three seconds, into a fifty-thousand
        element page. That is the load that made a reader turn JavaScript off,
        and the cap it slipped past is the one already here for exactly it.

        **Grouped by asset, so a row and its interior always move together.**
        Deferring a value while sending the positions beneath it would leave a
        row whose parts disagree about money - the fault `11f5e9f` was written
        to close. Each asset is admitted with everything it owns or waits with
        it, and an asset alone over budget still goes, or a single fat holding
        would block the queue behind it forever.

        :param payload: what the pass published, as `_payload` decoded it
        :type payload: dict
        :return: two-tuple of (payload, bool)
        """
        # **Integer keys out, string keys in the session.** The values map is
        # keyed by asset id and `_payload` decodes it with `strict_map_key=False`
        # to keep those integers - the fragments are addressed by them. A session
        # round-trips through JSON, which has no integer keys, so what is carried
        # comes back as `"31566704"` and has to be turned back before it can
        # merge with, or be ordered against, the `31566704` a later payload
        # brings.
        carry = self.request.session.get(self._carry_key()) or {}
        merged = {_asset_key(key): _bundle(held) for key, held in carry.items()}

        # What this block brings, overlaying the backlog per field: an asset
        # whose value moved again mid-resync supersedes the carried value, but
        # must not erase an amount or a position still waiting behind it.
        fresh = []
        for field, brought in (
            ("value", (payload.get("values") or {}).items()),
            ("amount", (payload.get("amounts") or {}).items()),
        ):
            for key, figure in brought:
                key = _asset_key(key)
                merged.setdefault(key, _bundle(None))[field] = figure
                fresh.append(key)
        for position in payload.get("positions") or ():
            key = _asset_key(position.get("asset"))
            merged.setdefault(key, _bundle(None))["positions"].append(position)
            fresh.append(key)

        if _fragments(merged) <= MAX_FRAGMENTS:
            self.request.session.pop(self._carry_key(), None)
            return _rebuilt(payload, merged), bool(merged)

        # **What moved this block goes first, and the backlog fills the rest.**
        # Ordering the whole queue by asset id would make a holding the reader
        # has just watched change wait its turn behind nine hundred that did
        # not - which is the complaint this whole mechanism is answering, not a
        # detail of it. A transfer a reader made themselves has to show up on
        # the next poll.
        seen, ordered = set(), []
        for key in fresh:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        ordered += sorted(
            (key for key in merged if key not in seen),
            key=lambda key: (isinstance(key, str), key),
        )

        # **The first asset that does not fit closes the poll**, rather than
        # being stepped over to top the budget up with cheaper ones behind it.
        # Skipping it would be free here and starve it indefinitely: a holding
        # with thirty positions would be passed by on every poll that had a
        # handful of ordinary values to spend the remainder on, and would be the
        # one row on the page that never came right.
        going, waiting, spent, full = {}, {}, 0, False
        for key in ordered:
            held = merged[key]
            cost = _fragments({key: held})
            if full or (going and spent + cost > MAX_FRAGMENTS):
                full = True
                waiting[str(key)] = held
                continue
            going[key] = held
            spent += cost
        self.request.session[self._carry_key()] = waiting
        return _rebuilt(payload, going), True

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
        context["positions"] = _named_positions(context.get("payload"))
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
