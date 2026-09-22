"""Module containing Alerts widget's views.

**The reader-facing half only.** Nothing here decides whether a rule has fired;
that is the engine's two evaluators, against numbers its own loops already
compute - see `notifications/DESIGN.md`. This stores what the reader asked for
and shows them what they have asked for.

**Never cached.** What these render is entirely per-reader: which rules *you*
keep, and how many more your tier allows. `address.html` is `cache_page`'d
across readers, which is why the control lives in `_swap_entry.html` and why
these responses must not be stored either.
"""

import hashlib
import hmac
import json
import logging

from api.widgets import bundle_and_addresses_from_path
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import TemplateView, View
from widgethost.enforcement import WidgetAccessMixin

from .evaluate import evaluate_page, evaluate_prices, payload_for
from .forms import UNIT_CHOICES, WINDOW_CHOICES, AlertRuleForm
from .manifest import MANIFEST
from .models import AlertRule, Direction, PushSubscription, Subject
from .population import publish_assets, publish_page
from .push import notify, push_configured
from .tiers import rules_allowed

logger = logging.getLogger(__name__)


class AlertsContextMixin:
    """Shared context: what this reader keeps, and what is left."""

    def alerts_context(self, address=""):
        """Return the modal's context for the current reader.

        **The allowance is sent as a remainder rather than a total**, so the
        template never subtracts. A second place doing that arithmetic is a
        second place to get it wrong.

        :param address: the bundle or address the modal was opened on
        :type address: str
        :return: dict
        """
        # **The page's own numbers, for the reader to aim at.** A threshold is
        # only meaningful next to what the figure is now, and the pass already
        # published both: `total` is the page's ALGO total and `priceusdc` is
        # what one ALGO is worth, which is also the rate a USD threshold is
        # converted at.
        #
        # None when the page has never been re-priced - it is in no live set -
        # and the template then shows no reference rather than a zero, which
        # would read as "your portfolio is worth nothing".
        published = payload_for(address) or {}

        user = self.request.user
        profile = getattr(user, "profile", None)
        allowed = rules_allowed(getattr(profile, "permission", 0))
        rules = list(
            AlertRule.objects.filter(user=user, active=True).order_by(
                "-created_at"
            )
        )
        return {
            "address": address,
            "rules": rules,
            "rules_allowed": allowed,
            "rules_kept": len(rules),
            "rules_left": max(0, allowed - len(rules)),
            "alerts_entitled": allowed > 0,
            "subjects": Subject.choices,
            "directions": Direction.choices,
            "windows": WINDOW_CHOICES,
            "units": UNIT_CHOICES,
            "widget_id": MANIFEST.id,
            # The public key is not secret - a subscription is bound to it, so
            # the browser must have it. The private one never leaves the server.
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            # Whether this deployment can send at all. A fork with no keys still
            # stores rules; the modal says so rather than offering a button that
            # cannot work.
            "push_configured": push_configured(),
            # Whether anything can reach this deployment to say a rule fired.
            # Without the shared secret both receiving endpoints refuse every
            # call, so no rule can fire however complete the code is - and the
            # modal says so rather than promising what this site cannot do.
            "alerts_live": bool(
                getattr(settings, "ALERTS_WEBHOOK_SECRET", "")
            ),
            "subscribed_browsers": PushSubscription.objects.filter(
                user=user
            ).count(),
            # Both in ALGO, as every threshold is stored.
            "current_total": published.get("total"),
            # ALGO's own price in USD. The form converts a USD threshold with
            # it, and the template shows the dollar equivalent beside the ALGO
            # one so a reader can see both without doing the arithmetic.
            "algo_usd": published.get("priceusdc"),
        }


@method_decorator(never_cache, name="dispatch")
class AlertsView(WidgetAccessMixin, AlertsContextMixin, TemplateView):
    """Render the alerts modal for an address or bundle page.

    Loaded on demand rather than shipped with every address page: the rule list
    is per-reader and changes as they edit it, so fetching it when the modal
    opens is both smaller and fresher than rendering it into the partial that
    carries the button.

    :var template_name: relative path to the Django template
    :var manifest: this widget's parsed manifest
    """

    template_name = "alerts/modal.html"
    manifest = MANIFEST
    bundle = None
    addresses = None

    def get_context_data(self, *args, **kwargs):
        """Expose the reader's rules and the form's choices.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context.update(self.alerts_context(self.bundle))
        return context

    def test_func(self):
        """Resolve bundle/addresses from the URL and apply the manifest gate.

        The manifest admits any authenticated profile; what a tier buys is how
        many rules may be kept. Gating the widget on the tier would render
        nothing for a reader who should be seeing an upgrade prompt.

        :return: Boolean
        """
        url_path = self.kwargs["page"].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return self.manifest_test_func(len(self.addresses.split(" ")))


@method_decorator(never_cache, name="dispatch")
class AlertsRulesView(WidgetAccessMixin, AlertsContextMixin, View):
    """Create a rule, and return the list it joined.

    **Returns markup rather than JSON**, because the caller is htmx swapping the
    list in place. A JSON endpoint would need a second renderer in JavaScript
    for a list the server already knows how to draw.

    :var manifest: this widget's parsed manifest
    """

    manifest = MANIFEST
    bundle = None
    addresses = None

    def post(self, request, *args, **kwargs):
        """Validate and store, then re-render the list.

        :return: :class:`django.http.HttpResponse`
        """
        form = AlertRuleForm(
            request.POST, user=request.user, address=self.bundle
        )
        if form.is_valid():
            form.save()
            status = 200
        else:
            # 422 rather than 400: the request was well-formed and the values
            # were not, which is what htmx's own error handling distinguishes.
            status = 422
        context = self.alerts_context(self.bundle)
        context["form"] = form if not form.is_valid() else AlertRuleForm(
            user=request.user, address=self.bundle
        )
        return self._render(request, context, status)

    def _render(self, request, context, status):
        """Render the panel that htmx swaps in.

        :return: :class:`django.http.HttpResponse`
        """
        return HttpResponse(
            render_to_string("alerts/_panel.html", context, request=request),
            status=status,
        )

    def test_func(self):
        """Resolve the page and apply the manifest gate.

        :return: Boolean
        """
        url_path = self.kwargs["page"].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return self.manifest_test_func(len(self.addresses.split(" ")))


@method_decorator(never_cache, name="dispatch")
class AlertsRuleDeleteView(WidgetAccessMixin, AlertsContextMixin, View):
    """Remove one of the reader's own rules.

    **Scoped to `request.user` in the lookup itself**, not checked afterwards.
    A rule id is a guessable integer, so fetching by id and then comparing
    owners is one forgotten line away from letting anybody delete anybody's
    alerts. `get_object_or_404(..., user=request.user)` cannot be forgotten
    that way: the wrong reader gets a 404, which is also the right answer.

    :var manifest: this widget's parsed manifest
    """

    manifest = MANIFEST
    bundle = None
    addresses = None

    def post(self, request, *args, **kwargs):
        """Delete the named rule and re-render the list.

        :return: :class:`django.http.HttpResponse`
        """
        rule = get_object_or_404(
            AlertRule, pk=self.kwargs["pk"], user=request.user
        )
        address = rule.address
        was_price_rule = rule.subject == Subject.ASA_PRICE
        rule.delete()
        # **The page's own address, not this view's bundle.** A rule stores the
        # page it was made from, and a reader may be deleting it from somewhere
        # else entirely - the modal lists every rule they keep, not just the
        # ones belonging to the page they happen to be on. Publishing
        # `self.bundle` here would leave the real page in `lvr` with no rules
        # and take one out that still has some.
        publish_page(address)
        # **Recomputed, not decremented.** The asset may still be named by
        # somebody else's rule, and `publish_assets` asks the database rather
        # than assuming - the same argument `publish_page` makes for pages.
        if was_price_rule:
            publish_assets()
        context = self.alerts_context(self.bundle)
        context["form"] = AlertRuleForm(user=request.user, address=self.bundle)
        return HttpResponse(
            render_to_string("alerts/_panel.html", context, request=request)
        )

    def test_func(self):
        """Resolve the page and apply the manifest gate.

        :return: Boolean
        """
        url_path = self.kwargs["page"].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return self.manifest_test_func(len(self.addresses.split(" ")))


@method_decorator(never_cache, name="dispatch")
class AlertsSubscribeView(WidgetAccessMixin, View):
    """Record the browser a reader wants notified on.

    **The browser decides the endpoint, not us.** `PushManager.subscribe()`
    returns a URL at Apple, Google or Mozilla plus the keys to encrypt for it;
    all this does is store what it was handed, against the reader who is signed
    in.

    **`update_or_create` on the endpoint, not `create`.** A browser re-sends the
    same subscription on every visit, so creating would either fail on the
    unique constraint or pile up rows. Keying on the endpoint also re-homes a
    subscription when a shared machine changes hands: the row follows the
    endpoint to whoever is signed in now, which is the only answer that does not
    send one reader's alerts to another.

    :var manifest: this widget's parsed manifest
    """

    manifest = MANIFEST

    def post(self, request, *args, **kwargs):
        """Store or refresh this browser's subscription.

        :return: :class:`django.http.JsonResponse`
        """
        try:
            body = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "Malformed subscription."}, status=400)

        endpoint = body.get("endpoint") or ""
        keys = body.get("keys") or {}
        if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
            return JsonResponse({"error": "Incomplete subscription."}, status=400)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh": keys["p256dh"],
                "auth": keys["auth"],
                # Truncated rather than validated: it is shown to the reader to
                # tell two browsers apart and is never parsed to decide
                # anything, so its only requirement is fitting the column.
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            },
        )
        return JsonResponse({"ok": True})

    def test_func(self):
        """Any authenticated profile may register a browser.

        The tier bands how many *rules* may be kept, not how many devices a
        reader signs in on - so this is the manifest gate and nothing more.

        :return: Boolean
        """
        return self.manifest_test_func(1)


@method_decorator(never_cache, name="dispatch")
class AlertsUnsubscribeView(WidgetAccessMixin, View):
    """Forget a browser, at that browser's request.

    **Scoped to the reader in the delete itself**, like the rule delete beside
    it: an endpoint is a long opaque string rather than a guessable integer, but
    scoping costs nothing and means a leaked endpoint cannot be used to
    unsubscribe somebody else.

    :var manifest: this widget's parsed manifest
    """

    manifest = MANIFEST

    def post(self, request, *args, **kwargs):
        """Remove this browser's subscription.

        :return: :class:`django.http.JsonResponse`
        """
        try:
            body = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "Malformed request."}, status=400)

        PushSubscription.objects.filter(
            user=request.user, endpoint=body.get("endpoint") or ""
        ).delete()
        # Idempotent: a browser unsubscribing twice, or one whose row was
        # already removed as gone, is not an error to report back.
        return JsonResponse({"ok": True})

    def test_func(self):
        """Any authenticated profile may remove their own browser.

        :return: Boolean
        """
        return self.manifest_test_func(1)


#: Header the engine signs its body with, mirroring the router monitor's.
SIGNATURE_HEADER = "HTTP_X_ASASTATS_ALERTS_SIGNATURE"


def signature_ok(request):
    """Whether this request carries our signature over exactly this body.

    **Three things, and each is a way this goes wrong quietly.**

    `compare_digest` rather than `==`, because a signature is the one place a
    timing comparison stops being theoretical.

    The bytes as received, never a re-serialisation: signing a parsed-and-
    re-encoded body is how a check comes to pass for a payload nobody sent.

    **An unset secret rejects.** The router monitor this copies signs only when
    it has a secret, which is right for a monitor and wrong here - without this
    branch, a deployment that had not configured one would expose an endpoint
    anybody could post rule firings to, and readers would be notified of things
    that never happened.

    :param request: the incoming request
    :return: Boolean
    """
    secret = getattr(settings, "ALERTS_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("alerts webhook called with no secret configured")
        return False
    offered = request.META.get(SIGNATURE_HEADER, "")
    expected = "sha256=" + hmac.new(
        secret.encode(), request.body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(offered, expected)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class AlertsRepricedView(View):
    """The engine saying a page it watches has moved.

    **No `WidgetAccessMixin`, and that is deliberate.** Every other view here is
    reached by a signed-in reader; this one is reached by the engine, which has
    no session and no user. Its credential is the signature over its body, and
    mixing the two gates would mean a machine caller needing a login.

    **It carries a trigger, not an answer.** The body says which page was
    re-priced; the numbers come from the Redis both projects already share, and
    the rules and their fire state never leave this database. See
    `notifications/DESIGN.md`.
    """

    def post(self, request, *args, **kwargs):
        """Evaluate the named page and notify whoever is owed an alert.

        :return: :class:`django.http.JsonResponse`
        """
        if not signature_ok(request):
            # 403 rather than 401: there is no authentication to retry with,
            # and a WWW-Authenticate header would invite one.
            return JsonResponse({"error": "Bad signature."}, status=403)

        try:
            body = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "Malformed body."}, status=400)

        page = body.get("page") or ""
        if not page:
            return JsonResponse({"error": "No page named."}, status=400)

        payload = payload_for(page)
        if payload is None:
            # The pass said it re-priced this page and published nothing we can
            # read. Not an error to report back at the engine - it did its part
            # - but it is the shape of a Redis problem, so it is logged.
            logger.warning("alerts: nothing published for %s", page)
            return JsonResponse({"ok": True, "fired": 0, "notified": 0})

        fired, skipped = evaluate_page(page, payload)
        if skipped:
            logger.info(
                "alerts: %s rule(s) on %s not evaluated here; see SKIPPED",
                skipped,
                page,
            )

        notified = _notify_all(fired, f"/{page}")
        return JsonResponse(
            {"ok": True, "fired": len(fired), "notified": notified}
        )


def _notify_all(fired, url):
    """Send one notification per fired rule and return how many landed.

    :param fired: the rules that crossed
    :type fired: list
    :param url: where the notification should open
    :type url: str
    :return: int
    """
    notified = 0
    for rule in fired:
        notified += notify(
            rule.user,
            {
                "title": "ASA Stats",
                "body": str(rule),
                # Per rule, so two alerts on one page replace neither. A shared
                # tag would silently collapse them into the last one.
                "tag": f"alert-{rule.pk}",
                "url": url,
            },
        )
    return notified


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class AlertsPricedView(View):
    """The engine handing over the prices of the assets rules name.

    **The one endpoint here whose body is an answer rather than a trigger.**
    `AlertsRepricedView` names a page and the numbers are read from the Redis
    both projects share; an asset's price is not there. It lives in the engine's
    *primary* cache, which the website has no client for - so the price arrives
    in the body, and the signature over that body is the only thing making it
    trustworthy. See `notifications/DESIGN.md`.

    The caller is the engine's periodic huey task, which reads which assets to
    price from `lvra` - published by `population.publish_assets`.
    """

    def post(self, request, *args, **kwargs):
        """Evaluate every `asa_price` rule these prices touch.

        :return: :class:`django.http.JsonResponse`
        """
        if not signature_ok(request):
            return JsonResponse({"error": "Bad signature."}, status=403)

        try:
            body = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "Malformed body."}, status=400)

        prices = body.get("prices")
        if not isinstance(prices, dict):
            return JsonResponse({"error": "No prices sent."}, status=400)

        # **Keys arrive as strings and the rules store integers.** JSON has no
        # integer keys, so a body that round-trips through `json.dumps` comes
        # back with `"31566704"` - and `prices.get(rule.asset_id)` would then
        # miss every asset silently, which reads exactly like "nothing moved".
        readings = {}
        for key, value in prices.items():
            try:
                readings[int(key)] = None if value is None else float(value)
            except (TypeError, ValueError):
                logger.warning("alerts: unusable price for asset %r", key)

        fired = evaluate_prices(readings)
        notified = _notify_all(fired, "/")
        return JsonResponse(
            {
                "ok": True,
                "assets": len(readings),
                "fired": len(fired),
                "notified": notified,
            }
        )
