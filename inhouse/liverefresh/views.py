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
import logging
import re
import time
from hashlib import blake2s

import msgpack
import redis
from rest_framework.exceptions import ValidationError
from django.core.cache import cache, caches
from django.core.cache.backends.dummy import DummyCache
from django_redis.exceptions import ConnectionInterrupted
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView

from api.position_id import identifying_link_ids, position_id_from_fields
from api.widgets import bundle_and_addresses_from_path
from utils.clients import redis_instance
from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS as MAX_FRAGMENTS
from utils.constants.core import LIVEREFRESH_RELOAD_COOLDOWN_SECONDS as RELOAD_COOLDOWN
from utils.layouts import layout_for_user
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin

from . import warmset
from .allowance import left, requires_linked_address, spend
from .manifest import MANIFEST
from .profiling import timed

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

#: The engine's list of recent payloads, newest first. See `CACHE_KEY_LIVE_BACKLOG`.
BACKLOG_PREFIX = "lvl"

logger = logging.getLogger("widgets.inhouse.liverefresh")

#: Drop carries this far beyond a normal resync and let a full payload heal them.
MAX_CARRY_FRAGMENTS = 50 * MAX_FRAGMENTS

#: A tab not heard from for this long has its per-tab state dropped; also the
#: cache lifetime of that state.
TAB_IDLE_SECONDS = 600
#: Tabs per bundle a reader keeps state for; the stalest goes first.
MAX_TABS = 8
#: Cache prefix of a reader's live state, `<prefix>:<user pk>:<key>`.
LIVE_STATE_PREFIX = "lvc"

_MISSING = object()


class LiveState:
    """A reader's live-refresh state in the cache, read like a session.

    Out of the session so a poll does not rewrite it every 3 s, and so a
    resync's carry cannot grow it. See docs/logbook.md.
    """

    def __init__(self, user_pk):
        self.prefix = f"{LIVE_STATE_PREFIX}:{user_pk}:"

    def get(self, key, default=None):
        value = cache.get(self.prefix + key, _MISSING)
        return default if value is _MISSING else value

    def __getitem__(self, key):
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        cache.set(self.prefix + key, value, TAB_IDLE_SECONDS)

    def __contains__(self, key):
        return self.get(key, _MISSING) is not _MISSING

    def pop(self, key, default=None):
        value = self.get(key, default)
        cache.delete(self.prefix + key)
        return value
#: What a `tab` parameter may be; anything else is treated as no tab at all.
_TAB_PATTERN = re.compile(r"[A-Za-z0-9]{1,16}")


def _pid(position):
    """Return the stable page id for a published position.

    :param position: live payload position
    :type position: dict
    :return: str
    """
    if isinstance(position, dict):
        identity = [
            position.get("asset"),
            position.get("fields"),
            position.get("links"),
        ]
        try:
            return str(
                position_id_from_fields(
                    position.get("asset"),
                    position.get("fields") or {},
                    identifying_link_ids(position.get("links")),
                )
            )
        except (TypeError, ValueError, AttributeError):
            pass
    else:
        identity = position
    # A malformed position must not take down a poll or change its id between retries.
    raw = json.dumps(identity, sort_keys=True, default=str)
    return "x-" + blake2s(raw.encode(), digest_size=8).hexdigest()


def _tab(request):
    """Return the `tab` the page sent, or "" when absent or malformed.

    :param request: the poll
    :type request: :class:`HttpRequest`
    :return: str
    """
    tab = request.GET.get("tab") or ""
    return tab if _TAB_PATTERN.fullmatch(tab) else ""


def _since(request):
    """Return the `since` the tab sent, or None when absent or malformed.

    :param request: the poll
    :type request: :class:`HttpRequest`
    :return: int or None
    """
    try:
        return int(request.GET.get("since"))
    except (TypeError, ValueError):
        return None


def _carry_size(carry):
    """Return a cheap upper bound on fragments in a carried backlog.

    :param carry: session carry keyed by asset
    :type carry: dict
    :return: int
    """
    if not isinstance(carry, dict):
        return MAX_CARRY_FRAGMENTS + 1
    size = 0
    for held in carry.values():
        if isinstance(held, dict):
            size += 2 + 2 * len(held.get("positions") or ())
        else:
            size += 1
    return size


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
        positions = held.get("positions") or {}
        if not isinstance(positions, dict):
            # Old format: list that can hold duplicates. Deduplicate by pid.
            positions = {_pid(p): p for p in positions}
        else:
            # Re-key on load so a PID recipe change cannot retain stale copies.
            positions = {_pid(position): position for position in positions.values()}
        return {
            "value": held.get("value"),
            "amount": held.get("amount"),
            "positions": positions,
        }
    return {"value": held, "amount": None, "positions": {}}


def recent_log_events(path_value):
    """Return the events of the last payloads published for a page, newest first.

    The live log is empty when a page loads, and a reload is what a holdings
    change causes, so a row that arrived by reload would vanish without this.
    The engine keeps the last `LIVE_BACKLOG_LENGTH` payloads for each page, and
    each carries its own events, so reading them back restores the recent log.
    A page with no backlog, or no Redis, has nothing to restore and gets none.

    :param path_value: the address or bundle as the URL carries it
    :type path_value: str
    :return: list of dict
    """
    try:
        # `force_bundle=False` for the same reason as the poll: one address is
        # published under its own name, and only several are hashed.
        bundle, _addresses = bundle_and_addresses_from_path(path_value, force_bundle=False)
        items = redis_instance().lrange(f"{BACKLOG_PREFIX}:{bundle}", 0, -1)
    except ValidationError:
        # not a page this widget watches, so there is no backlog to read
        return []
    except (redis.exceptions.RedisError, ConnectionInterrupted):
        logger.warning("live log backlog unreadable for %s", str(path_value)[:6])
        return []
    events = []
    for raw in items:
        try:
            payload = msgpack.unpackb(raw, strict_map_key=False)
        except (ValueError, TypeError, msgpack.UnpackException):
            continue
        if not isinstance(payload, dict):
            continue
        # a payload's events are oldest first, the log is newest first
        events.extend(reversed(payload.get("events") or ()))
    return events


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
        for position in (held.get("positions") or {}).values():
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
            for position in (held.get("positions") or {}).values()
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
    named = []
    for position in (payload or {}).get("positions") or ():
        asset_id = position.get("asset")
        if asset_id is None:
            continue
        fields = position.get("fields") or {}
        kind = fields.get("type") or ""
        name = fields.get("name") or ""
        band = (
            "balance"
            if kind == "Balance"
            else "staked"
            if kind == "Staked" and "farm" not in name
            else "liquidity"
            if kind == "Added" and name == "Liquidity"
            else "defi"
        )
        named.append(
            dict(
                position,
                band=band,
                pid=position_id_from_fields(
                    asset_id,
                    fields,
                    identifying_link_ids(position.get("links")),
                ),
            )
        )
    return named


def _digest(fingerprint):
    """Return the part of `fingerprint` that says which *assets* are held.

    `<counter>:<assets>:<positions>` - the counter is how many times the account
    has been struck, and the two digests are the two things a fragment cannot
    express, kept apart because they cost the reader different amounts. Only the
    asset set needs the page rebuilt.

    An older two-part fingerprint, or any shape without a separator, is returned
    whole: comparing it against itself still works, and guessing at it would
    not. During a deploy a page rendered under one shape and a payload published
    under the other simply differ, which is one reload.

    :param fingerprint: what `_holdings_fingerprint` made
    :type fingerprint: str
    :return: str
    """
    parts = fingerprint.split(":")
    return parts[1] if len(parts) > 2 else parts[-1]


def _positions_digest(fingerprint):
    """Return the part of `fingerprint` that says which *positions* are held.

    **"" is "cannot tell", and it is not the same as "no positions".** A
    fingerprint from before the split has no third part and a page that sent
    none has no parts at all, and in both cases the only safe answer is the
    reload that preceded the regroup path entirely. So the caller checks for
    truth, never just for inequality - two empty strings comparing equal would
    silently claim the positions match.

    :param fingerprint: what `_holdings_fingerprint` made, or None
    :type fingerprint: str
    :return: str
    """
    parts = (fingerprint or "").split(":")
    return parts[2] if len(parts) > 2 else ""


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
    tab = ""
    live_state = None

    def get(self, request, *args, **kwargs):
        """Return the changed fragments, or 204 when nothing moved.

        **204 rather than an empty body**: htmx leaves the page alone on a 204,
        so a block that moved nothing costs one request and no DOM work, which
        is most blocks for most pages. Redis failures return 204 too: the poll
        is a heartbeat, not a contract; a missed block is answered by the next.

        :return: :class:`HttpResponse`
        """
        try:
            return self._get(request, *args, **kwargs)
        except (redis.exceptions.RedisError, ConnectionInterrupted):
            logger.warning(
                "liverefresh: Redis failure on poll for %s",
                self.bundle or self.kwargs.get("value"),
            )
            return HttpResponse(status=204)

    def _get(self, request, *args, **kwargs):
        client = redis_instance()
        # One timestamp for one poll, so the heartbeat and the paid mark
        # carry the same score and the two sets cannot age out of step.
        now = time.time()
        self.tab = _tab(request)
        self._touch_tab(now)
        spans = {}
        with timed(spans, "heartbeat"):
            warm = self._heartbeat(client, now)

        # **Read first, charge later.** What is left decides whether this
        # reader is paying and whether they have run out, both of which are
        # answered before the payload is read. `left` spends nothing.
        with timed(spans, "left"):
            remaining_seconds = self._left(client)

        if not warm:
            # **Over this reader's warm-set cap**, so the page is not kept
            # alive for them and cannot move: not charged, and not marked paid
            # either, since `lvq` would ask the engine to prioritise a page we
            # deliberately did not subscribe. 204 rather than the spent
            # response - they have run out of nothing, and their other tabs are
            # still live.
            return self._attach_spans(
                self._with_left(HttpResponse(status=204), remaining_seconds), spans
            )

        if remaining_seconds is None:
            # **No daily limit means this reader is paying for it.** Same
            # score and 90-second ageing as `lvx`, so a page stops counting as
            # paid 90 s after the last subscriber closes it.
            #
            # **Marked before the payload is read.** This is what lifts a page
            # over the admission budget, and an unadmitted page is never
            # published - so gating the mark on something having been published
            # would make a shed page's shedding permanent.
            client.zadd(PAID_KEY, {self.addresses: now})
        elif remaining_seconds <= 0:
            # Told before the payload is read, and never folded into the 204
            # below: a reader who is out must be told, or the widget keeps
            # polling and `address.js` never takes the plain reload back up.
            return self._attach_spans(self._spent_response(), spans)

        payload = self._payload(client)
        if payload is None:
            # **Nothing published, so nothing is charged.** The pass may not
            # have reached this page, or it was shed by admission control and
            # its payload aged out behind it; a deployment with no live pass at
            # all is the same shape. `left` reads the balance without spending,
            # so the badge still shows the truth while the reader waits.
            return self._attach_spans(
                self._with_left(HttpResponse(status=204), remaining_seconds), spans
            )

        # Delivered, so charged. This is the only call that spends.
        with timed(spans, "allowance"):
            remaining_seconds = self._allowance(client, now)
        if remaining_seconds is not None and remaining_seconds <= 0:
            return self._attach_spans(self._spent_response(), spans)

        seq = payload.get("seq")
        with timed(spans, "caught_up"):
            payload = self._caught_up(client, payload, _since(request))

        with timed(spans, "reload_response"):
            reload = self._reload_response(request, payload)
        if reload is not None:
            # The page is about to be re-rendered whole, so anything still
            # queued describes markup that will not exist in a moment.
            self._live.pop(self._carry_key(), None)
            return self._attach_spans(self._with_left(reload, remaining_seconds), spans)

        with timed(spans, "regroup_wanted"):
            regroup = self._regroup_wanted(request, payload)

        with timed(spans, "chunked"):
            payload, sending = self._chunked(payload)

        # **`sending` first**, because a resync can outlive the block that
        # started it: the total settles while values are still going out, and a
        # 204 then would strand the rest of them.
        # an event is news even when the total did not move: see docs/logbook.md
        if (
            not sending
            and not payload.get("events")
            and payload.get("total") == self._last_total()
        ):
            return self._attach_spans(
                self._with_seq(
                    self._regrouping(
                        self._with_left(HttpResponse(status=204), remaining_seconds),
                        regroup,
                    ),
                    seq,
                ),
                spans,
            )

        self._live[self._session_key()] = payload.get("total")
        with timed(spans, "context_and_render"):
            context = self.get_context_data(payload=payload, **kwargs)
            response = self.render_to_response(context)
        response = self._regrouping(
            self._with_left(response, remaining_seconds),
            regroup,
        )
        return self._attach_spans(self._with_seq(response, seq), spans)

    def _caught_up(self, client, payload, since):
        """Return `payload` with every diff this tab missed folded in beneath it.

        A diff is relative to the payload before it, so a tab that skipped one
        would keep that block's rows while the absolute band moved on. `since`
        is the last `seq` the tab applied. See docs/logbook.md.

        :param client: Redis client instance
        :type client: :class:`Redis`
        :param payload: the latest payload, as `_payload` decoded it
        :type payload: dict
        :param since: the tab's last applied `seq`, or None
        :type since: int or None
        :return: dict
        """
        import msgpack

        seq = payload.get("seq")
        if not isinstance(seq, int) or since is None or since > seq:
            return payload
        if since == seq:
            # already applied; only the carry, if any, is still owed
            return dict(payload, values={}, amounts={}, positions=[], events=[])
        if seq - since == 1:
            return payload

        missed = {}
        for raw in client.lrange(f"{BACKLOG_PREFIX}:{self.bundle}", 0, -1):
            try:
                older = msgpack.unpackb(raw, strict_map_key=False)
            except (ValueError, TypeError, msgpack.UnpackException):
                continue
            number = older.get("seq") if isinstance(older, dict) else None
            if isinstance(number, int) and since < number < seq:
                missed[number] = older
        if len(missed) != seq - since - 1:
            logger.debug(
                "liverefresh: %s missed %d payloads, %d still held",
                self.bundle[:6],
                seq - since - 1,
                len(missed),
            )

        values, amounts, positions, events = {}, {}, {}, []
        # oldest first, so a later figure for the same row wins. Events are
        # not keyed: each one happened once, in the block that published it.
        for each in [missed[number] for number in sorted(missed)] + [payload]:
            values.update(each.get("values") or {})
            amounts.update(each.get("amounts") or {})
            events.extend(each.get("events") or ())
            for position in each.get("positions") or ():
                positions[_pid(position)] = position
        return dict(
            payload,
            values=values,
            amounts=amounts,
            positions=list(positions.values()),
            events=events,
        )

    @staticmethod
    def _with_seq(response, seq):
        """Tell the tab which payload it now has, through `liverefresh:seq`.

        :param response: the response this poll is about to return
        :type response: :class:`HttpResponse`
        :param seq: the latest payload's `seq`, or None from an older engine
        :type seq: int or None
        :return: :class:`HttpResponse`
        """
        if not isinstance(seq, int):
            return response
        triggers = json.loads(response.get("HX-Trigger") or "{}")
        triggers["liverefresh:seq"] = {"seq": seq}
        response["HX-Trigger"] = json.dumps(triggers)
        return response

    @staticmethod
    def _regrouping(response, wanted):
        """Ask the reader's page for its positions, when they are out of date.

        **On the 204 as well as on a body, and that is not symmetry for its own
        sake.** A position can open on a block that moves no figure this page
        renders - a stake of an amount the row already showed, on an asset whose
        price sat still - and that poll answers 204. Attaching this only to a
        response with fragments in it would leave exactly that reader waiting
        for an unrelated price to move before their new row appeared.

        `HX-Trigger` rather than a body, because what this asks for is a second
        request carrying something only the browser has.

        :param response: the response this poll is about to return
        :type response: :class:`HttpResponse`
        :param wanted: whether the positions are out of date
        :type wanted: bool
        :return: :class:`HttpResponse`
        """
        if not wanted:
            return response
        # Merged rather than assigned: `_with_left` has usually written the
        # allowance into this header, and overwriting it would stop the badge
        # for as long as a regroup is pending.
        triggers = json.loads(response.get("HX-Trigger") or "{}")
        triggers["liverefresh:regroup"] = {}
        response["HX-Trigger"] = json.dumps(triggers)
        return response

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

    def _attach_spans(self, response, spans):
        """Attach profiling spans without replacing the response's triggers.

        :param response: response being returned to htmx
        :param spans: elapsed seconds keyed by operation name
        :return: :class:`HttpResponse`
        """
        if not spans:
            return response
        hx_trigger = response.get("HX-Trigger") or "{}"
        # Don't modify special HX-Trigger values that are part of the public API contract
        special_triggers = {
            "liverefresh:spent",
            "liverefresh:left",
            "liverefresh:regroup",
            "liverefresh:regrouped",
        }
        if hx_trigger in special_triggers:
            return response
        # Don't add spans to 204 responses that have no HX-Trigger (e.g., unlimited reader with no payload)
        if response.status_code == 204 and "HX-Trigger" not in response:
            return response
        try:
            triggers = json.loads(hx_trigger)
        except json.JSONDecodeError:
            triggers = {}
        triggers["liverefresh:spans"] = {k: f"{v:.3f}s" for k, v in spans.items()}
        response["HX-Trigger"] = json.dumps(triggers)
        # Log spans for latency analysis
        logger.debug(
            "liverefresh spans: %s",
            ", ".join(f"{k}={v:.3f}s" for k, v in spans.items()),
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

        # **Only the asset *set* reaches this far; the counter does not.** The
        # counter steps on every block that strikes the account, so comparing
        # whole fingerprints rebuilds a transacting account's page on almost
        # every block to correct figures the fragments already carry.
        #
        # **Narrowing it is only safe while a position is addressable and
        # published**: `pq-<pid>` and `pv-<pid>` on the page, `positions` in the
        # payload, and a handler carrying the new figure up to the
        # `.position`'s own `data-value`. Without all three, the positions
        # inside a row freeze while the total above them stays live.
        #
        # Two cases still rebuild. A genuinely new asset has no row for a
        # fragment to land in, and a position the page could not name gets no id
        # and no fragment. A position *arriving* is handled a level down by
        # `_regroup_wanted`, which re-renders one venue group.
        if _digest(rendered) == _digest(published):
            return None

        # Refusing here rather than in the script: the reader's page has no way
        # to know how often it has been told to reload, and a client-side guard
        # would have to survive the very reloads it is counting.
        now = time.time()
        last = self.request.session.get(self._reload_key())

        # **A gap clears it, which is what makes this a cooldown rather than a
        # deadline.** The stamp lives in the session and so survives the tab
        # being closed, which would otherwise refuse a reader the reload they
        # came back genuinely needing.
        #
        # **Keying on the fingerprint instead does not work.** The counter steps
        # on every block that strikes the account, so in a runaway the
        # fingerprint differs on every pass and a fingerprint key waves every
        # reload through - the bug this was written for.
        #
        # What separates the two cases is how continuously, not what changed: a
        # runaway is found stale on essentially every poll so the gap never
        # opens, while a closed window is not polling at all. Recorded here and
        # not on every poll, because the question is when this reader was last
        # *found stale*.
        stale = self.request.session.get(self._stale_key())
        if stale and now - stale > RELOAD_COOLDOWN:
            last = None
        self.request.session[self._stale_key()] = now

        # **The detector's input, before anything is trusted.** One line per
        # decision; a reload is rare enough that this stays quiet on a healthy
        # page, and if it is not quiet that is the finding.
        logger.debug(
            "live reload %s: page %s engine %s (%s), %s",
            self.bundle[:6],
            rendered,
            published,
            "assets differ" if _digest(rendered) != _digest(published) else "same assets",
            (
                "held by the cooldown"
                if last and now - last < RELOAD_COOLDOWN
                else "ordered"
            ),
        )

        if last and now - last < RELOAD_COOLDOWN:
            # Fragments still go out; the reader keeps getting live figures
            # while the row structure waits for the cooling-off to pass.
            return None
        self.request.session[self._reload_key()] = now

        response = HttpResponse(status=200)
        response["HX-Refresh"] = "true"
        return response

    @staticmethod
    def _regroup_wanted(request, payload):
        """Return whether the reader's positions are out of date, not their assets.

        **The case the reload was covering and should not have been.** Opening a
        Mallow position on an account that already holds USDC adds a row inside a
        row the page already has: no asset arrived, so nothing needs rebuilding,
        but a value fragment reaches only elements that exist and there is no
        element yet. Until the two digests were published apart this was
        indistinguishable from buying a new asset, and the reader lost their
        scroll, their filters and every open section to a full reload for it.

        **Asked for rather than answered here.** This poll knows the reader's
        fingerprint and not their positions - a digest is not a list - so it
        cannot say which groups to send. `LiveRegroupView` is told, once per
        change rather than every three seconds.

        Both digests must be present. An absent one is a fingerprint from before
        the split, and the answer there is the reload that came before all this.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :param payload: what the pass last published for this page
        :type payload: dict
        :return: bool
        """
        rendered = request.GET.get("holdings") or ""
        published = payload.get("holdings") or ""
        mine = _positions_digest(rendered)
        theirs = _positions_digest(published)
        if not mine or not theirs:
            return False
        # The asset half deliberately not compared: a page whose assets also
        # moved is getting `HX-Refresh` from `_reload_response` before this runs.
        return mine != theirs

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

        # **Derived when the engine did not send it.** The two services deploy
        # separately, so a payload from an older engine is a real case, and the
        # band reads every figure it shows off this payload - a missing key is
        # a figure the reader watches go blank.
        if not payload.get("pricealgo") and payload.get("priceusdc"):
            payload["pricealgo"] = 1 / payload["priceusdc"]
        return payload

    @property
    def _live(self):
        """This reader's per-tab state; a plain dict stands in for it in tests."""
        if self.live_state is None:
            # a DummyCache (development) drops every write; the session keeps them
            self.live_state = (
                self.request.session
                if isinstance(caches["default"], DummyCache)
                else LiveState(getattr(self.request.user, "pk", None))
            )
        return self.live_state

    def _session_key(self, tab=None):
        """Key holding the total this tab was last shown."""
        tab = self.tab if tab is None else tab
        return f"liverefresh:{self.bundle}" + (f":{tab}" if tab else "")

    def _tabs_key(self):
        """Key holding {tab: last poll time} for this bundle."""
        return f"liverefresh:tabs:{self.bundle}"

    def _touch_tab(self, now):
        """Record this tab's poll and drop the state of tabs gone idle.

        The last total and the carry are per tab, so two tabs on one bundle do
        not take each other's fragments. See docs/logbook.md.

        :param now: unix time of this poll
        :type now: float
        """
        if not self.tab:
            return
        session = self._live
        tabs = dict(session.get(self._tabs_key()) or {})
        tabs[self.tab] = now
        keep = sorted(
            (tab for tab, seen in tabs.items() if now - seen <= TAB_IDLE_SECONDS),
            key=tabs.get,
            reverse=True,
        )[:MAX_TABS]
        for gone in set(tabs) - set(keep):
            session.pop(self._session_key(gone), None)
            session.pop(self._carry_key(gone), None)
        session[self._tabs_key()] = {tab: tabs[tab] for tab in keep}

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

    def _carry_key(self, tab=None):
        """Key holding the values this tab is still owed for this page."""
        tab = self.tab if tab is None else tab
        return f"liverefresh:carry:{self.bundle}" + (f":{tab}" if tab else "")

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
        # keyed by asset id and the fragments are addressed by those integers,
        # but a session round-trips through JSON, which has none - so a carried
        # key comes back as `"31566704"` and has to be turned back before it can
        # merge with the `31566704` a later payload brings.
        carry = self._live.get(self._carry_key()) or {}
        # Drop any runaway backlog: old list-format carries grow without
        # limit; a session over the cap is discarded safely (next full payload
        # rebuilds it, regroup/reload heals the page).
        carry_size = _carry_size(carry)
        if carry_size:
            logger.debug(
                "liverefresh carry_frag=%d bundle=%s",
                carry_size,
                self.bundle[:6],
            )

        if carry_size > MAX_CARRY_FRAGMENTS:
            logger.warning(
                "liverefresh: dropping runaway carry for %s (%d)",
                self.bundle[:6],
                carry_size,
            )
            self._live.pop(self._carry_key(), None)
            carry = {}
        merged = {_asset_key(key): _bundle(held) for key, held in carry.items()}

        # Overlaid per field: an asset whose value moved again mid-resync
        # supersedes the carried value, but must not erase an amount or a
        # position still waiting behind it.
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
            entry = merged.get(key)
            if entry is None:
                entry = merged[key] = _bundle(None)
            entry["positions"][_pid(position)] = position
            fresh.append(key)

        if _fragments(merged) <= MAX_FRAGMENTS:
            self._live.pop(self._carry_key(), None)
            return _rebuilt(payload, merged), bool(merged)

        # **What moved this block goes first, and the backlog fills the rest.**
        # Ordering the whole queue by asset id would make a holding the reader
        # just watched change wait behind nine hundred that did not.
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
        # being stepped over for cheaper ones behind it. Skipping would starve
        # it indefinitely: a holding with thirty positions would be passed by on
        # every poll with ordinary values to spend the remainder on.
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
        self._live[self._carry_key()] = waiting
        return _rebuilt(payload, going), True

    def _last_total(self):
        """Return the total this reader was last shown, or None."""
        return self._live.get(self._session_key())

    def get_context_data(self, *args, **kwargs):
        """Expose the published payload to the fragment template.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["addresses"] = self.addresses
        context["bundle"] = self.bundle
        # **The same helper the address page keys its cache entry on.** The
        # fragments address ids only one layout renders, so the wrong set means
        # every swap lands nowhere. Derived here rather than taken from a
        # parameter, so the two cannot disagree.
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
        # - the raw address for one, the hash for several. Hashing
        # unconditionally here asks for a key nothing writes, and the failure is
        # silent: the poll still heartbeats, so every response is a 204 over a
        # live indicator and nothing logs a problem.
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            self.kwargs.get("value") or self.args[0], force_bundle=False
        )
        if not self.manifest_test_func(len(self.addresses.split())):
            return False

        # **The free tier may only watch an address it has connected.** The
        # free allowance is spent per address so that farming accounts buys
        # nothing; without this, an abuser needs no accounts at all, only a list
        # of other people's addresses, each arriving with a fresh allowance.
        #
        # Self-scoped by `linked_addresses_for_user`, which reads only the
        # requesting user's own rows and is never an oracle for whose address
        # this is. Paid tiers are unaffected.
        profile = getattr(self.request.user, "profile", None)
        if requires_linked_address(getattr(profile, "permission", 0) or 0):
            return all(
                is_linked_to_user(self.request.user, address)
                for address in self.addresses.split()
            )
        return True


def _snapshot_account(value, addresses, client=None):
    """Return `(account, fingerprint)` for a page, or `(None, "")`.

    **The snapshot and never the engine call.** `fetch_and_serialize_account`
    falls back to asking the engine when no snapshot is published, which is the
    right answer for a page being rendered and the wrong one here: a regroup is
    an optimisation over a reload, and buying it with a synchronous engine call
    on a poll's back would make the fast path the expensive one. No snapshot
    means no regroup, and the reload is what happens instead.

    Positions are annotated with their `pid` for the same reason `api.main`
    annotates the snapshot it serves: the engine does not emit one, and a group
    rendered without them has no `data-pid`, no pin control and nothing for the
    next block's value fragments to land on.

    An unstamped snapshot is refused. The widget writes the fingerprint it has
    caught up to back onto the page, and doing that from a snapshot that cannot
    say which one it is would leave wrong rows with nothing left to notice them.

    :param value: single address, or the bundle hash from the path
    :type value: str
    :param addresses: space-joined addresses for a multi-address bundle
    :type addresses: str
    :param client: Redis client instance, for tests
    :type client: :class:`Redis`
    :return: tuple of (dict, str)
    """
    from api.live import stamped_snapshot
    from api.position_id import annotate_positions

    stamped = stamped_snapshot(value, addresses, client)
    if not stamped:
        return None, ""
    account, holdings = stamped
    if not account or not holdings:
        return None, ""
    for item in account.get("asaitems") or ():
        annotate_positions((item.get("asset") or {}).get("id"), item.get("programs"))
    return account, holdings


def _asaitem_id(asaitem):
    """Return an asaitem's asset id as the string a `data-owner` carries.

    :param asaitem: one entry from a serialized account's `asaitems`
    :type asaitem: dict
    :return: str
    """
    return str((asaitem.get("asset") or {}).get("id"))


def _pids_of(asaitem):
    """Return the position ids an asaitem's group would render with.

    **Ambiguous positions are excluded, and they have to be.** A position the
    page could not name renders no `data-pid` - three on the reference bundle
    are genuinely indistinguishable - so it is absent from what the browser
    sends back. Counting it here would make every asset holding one differ on
    every regroup, for ever, and re-render a group that had not changed.

    :param asaitem: one entry from a serialized account's `asaitems`
    :type asaitem: dict
    :return: frozenset
    """
    return frozenset(
        program.get("pid")
        for program in asaitem.get("programs") or ()
        if program.get("pid") and not program.get("pid_ambiguous")
    )


def _sent_pids(raw):
    """Return `{asset id: {pid}}` from what the reader's page sent.

    **Each token is `<asset id>:<pid>`, and the asset is sent rather than parsed
    out of the pid.** A pid's internals belong to `api.position_id`, which is
    free to change how it builds one; the page already knows which asset a row
    belongs to, because `data-owner` is on the row for the toolbar's sake. So
    the browser says it and nothing here has to know the format.

    Anything malformed is dropped rather than rejected. This is an optimisation
    over a reload: a body this cannot read means some group looks changed, which
    re-renders a group that did not need it, and the reload is still behind that
    if the page really is wrong.

    :param raw: the `pids` field, as the page posted it
    :type raw: str
    :return: dict
    """
    sent = {}
    for token in (raw or "").split():
        asset, separator, pid = token.partition(":")
        if asset and separator and pid:
            sent.setdefault(asset, set()).add(pid)
    return {asset: frozenset(pids) for asset, pids in sent.items()}


@method_decorator(never_cache, name="dispatch")
class LiveRegroupView(LiveRefreshView):
    """POST /widgets/liverefresh/<value>/regroup -> the venue groups that moved.

    **What the poll cannot answer, because only the browser knows the question.**
    A position opening or closing changes a row *inside* a row the page already
    has. The poll knows the reader's fingerprint, which is a digest and not a
    list, so it can tell that the positions moved and not which ones - and the
    engine's diff describes figures, not rows. This is told: the page sends the
    `data-pid` of every position it is carrying, and what comes back is the
    `.program-groups` of each asset whose set differs, swapped out of band.

    **The group and not the row, which is not a matter of taste.** A group has a
    heading, a count and a subtotal that appears only above two positions, so a
    row arriving changes three things outside itself. Sending the row would
    leave a group of two labelled as a group of one with no subtotal.

    Rendered from the *snapshot* rather than from the diff, because the diff
    carries none of that - and the snapshot is the address page's own structure,
    so the group is built by the template that built it in the first place
    rather than by a second description of a position in JavaScript.

    Inherits the poll's gate: the same manifest band, the same linked-address
    rule, the same page resolution. It spends no allowance - the reader has
    already paid for the poll that asked for this, and charging twice for one
    block's news would be charging for our own message.
    """

    template_name = "liverefresh/regroup.html"
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        """Return the changed groups, or 204 when none of them changed.

        A Redis failure here is also a 204: the regroup is an optimisation, and
        the next poll will ask again once the connection recovers.

        :return: :class:`HttpResponse`
        """
        try:
            return self._post(request, *args, **kwargs)
        except (redis.exceptions.RedisError, ConnectionInterrupted):
            logger.warning(
                "liverefresh regroup: Redis failure on %s",
                self.kwargs.get("value") or self.args[0],
            )
            return HttpResponse(status=204)

    def _post(self, request, *args, **kwargs):
        """Run regroup logic without the outer Redis-error handling."""
        if layout_for_user(getattr(request, "user", None)) == "classic":
            # The classic layout renders no positions at all, so there is no
            # group to send and nothing that a regroup would mean.
            return HttpResponse(status=204)

        account, holdings = _snapshot_account(
            self.kwargs.get("value") or self.args[0], self.addresses, redis_instance()
        )
        if not account:
            # **No snapshot is not an error, it is the previous behaviour.** The
            # page keeps the fingerprint it has, so the next poll finds it stale
            # again and `_reload_response` rebuilds the page as it always did.
            return HttpResponse(status=204)

        mine = _sent_pids(request.POST.get("pids"))
        changed = [
            item
            for item in account.get("asaitems") or ()
            if _pids_of(item) != mine.get(_asaitem_id(item), frozenset())
        ]
        context = self.get_context_data(changed=changed, holdings=holdings, **kwargs)
        response = self.render_to_response(context)
        # What the page has caught up to, so the next poll stops asking. Taken
        # from the snapshot and never from what was last published: rendering
        # one fingerprint's rows while claiming another's leaves a page wrong
        # with no mismatch left to find it.
        response["HX-Trigger"] = json.dumps(
            {"liverefresh:regrouped": {"holdings": holdings}}
        )
        return response
