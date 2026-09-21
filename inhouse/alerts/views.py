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

from api.widgets import bundle_and_addresses_from_path
from django.conf import settings
import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.base import TemplateView, View
from widgethost.enforcement import WidgetAccessMixin

from .forms import WINDOW_CHOICES, AlertRuleForm
from .manifest import MANIFEST
from .push import push_configured
from .models import AlertRule, Direction, PushSubscription, Subject
from .tiers import rules_allowed


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
            "widget_id": MANIFEST.id,
            # The public key is not secret - a subscription is bound to it, so
            # the browser must have it. The private one never leaves the server.
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            # Whether this deployment can send at all. A fork with no keys still
            # stores rules; the modal says so rather than offering a button that
            # cannot work.
            "push_configured": push_configured(),
            "subscribed_browsers": PushSubscription.objects.filter(
                user=user
            ).count(),
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
        url_path = self.args[0].upper()
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
        url_path = self.args[0].upper()
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
        rule.delete()
        context = self.alerts_context(self.bundle)
        context["form"] = AlertRuleForm(user=request.user, address=self.bundle)
        return HttpResponse(
            render_to_string("alerts/_panel.html", context, request=request)
        )

    def test_func(self):
        """Resolve the page and apply the manifest gate.

        :return: Boolean
        """
        url_path = self.args[0].upper()
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
