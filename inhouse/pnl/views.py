"""Module containing the profit and loss widget's views."""

import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView, View

from api.client import engine_request
from api.widgets import bundle_and_addresses_from_path
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin
from widgethost.manifest import addresses_limit_for_permission
from widgets.inhouse.historic.consumers import _restore_event_phase_keys
from widgets.inhouse.alerts.forms import AlertRuleForm
from widgets.inhouse.alerts.models import Subject
from widgets.inhouse.historic.structs import UpdateStatus

from .display import asset_label, event_row, period_summary, summary, table_row
from .manifest import MANIFEST
from .models import PnlBundle
from .tiers import features_for

ADDRESSES_LIMIT_ERROR = (
    "Your <a href='/subscriptions/' target='_blank' rel='noopener'>subscription tier"
    "</a> allows profit and loss for up to %s address(es)."
)
PERIOD_LABELS = {
    "all": "All time",
    "ytd": "This year",
    "30d": "30 days",
    "7d": "7 days",
}
LINKED_ONLY_ERROR = (
    "Without a subscription, profit and loss is available for one address you "
    "have linked to your account."
)


def _permission(user):
    """Return `user` profile's permission, zero without one.

    :param user: request's user
    :type user: :class:`django.contrib.auth.models.User`
    :return: int
    """
    return getattr(getattr(user, "profile", None), "permission", 0) or 0


def _engine(scope, method, bundle, suffix="", **kwargs):
    """Call the engine's P&L endpoint `scope` for `bundle` and return its JSON.

    :param scope: P&L endpoint scope
    :type scope: str
    :param method: HTTP method
    :type method: str
    :param bundle: bundle hash
    :type bundle: str
    :param suffix: path part after the bundle
    :type suffix: str
    :return: dict or None
    """
    response = engine_request(
        scope,
        method,
        f"/api/v2/pnl/{bundle}/{suffix}",
        MANIFEST.engine_endpoints,
        **kwargs,
    )
    return response.json() if response.content else None


def period_start(period, now=None):
    """Return the first second of `period`, or None for all-time.

    :param period: one of the keys of `PERIOD_LABELS`
    :type period: str
    :param now: current seconds since epoch
    :type now: int
    :return: int or None
    """
    now = now or int(time.time())
    if period == "ytd":
        return int(
            datetime(datetime.fromtimestamp(now, UTC).year, 1, 1, tzinfo=UTC).timestamp()
        )

    days = {"30d": 30, "7d": 7}.get(period)
    return now - days * 86400 if days else None


def addresses_in_use(user, exclude_bundle=None):
    """Return how many addresses `user` keeps across P&L bundles.

    :param user: request's user
    :type user: :class:`django.contrib.auth.models.User`
    :param exclude_bundle: bundle left out of the count
    :type exclude_bundle: str
    :return: int
    """
    bundles = PnlBundle.objects.filter(user=user)
    if exclude_bundle:
        bundles = bundles.exclude(bundle=exclude_bundle)

    return bundles.aggregate(total=Sum("address_count"))["total"] or 0


class PnlAccessMixin(WidgetAccessMixin):
    """Gate shared by the widget's views: manifest band, then linked address.

    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    manifest = MANIFEST
    bundle = None
    addresses = None

    @property
    def features(self):
        """Return the features the reader's tier unlocks.

        :return: dict
        """
        return features_for(_permission(self.request.user))

    def currency(self):
        """Return the requested denomination if the tier allows it, else USD.

        :var currency: requested denomination
        :type currency: str
        :return: str
        """
        currency = self.request.GET.get("currency", "usd")
        return currency if currency in self.features["currencies"] else "usd"

    def period(self):
        """Return the requested period if the tier allows it, else all-time.

        :var period: requested period
        :type period: str
        :return: str
        """
        period = self.request.GET.get("period", "all")
        return period if period in self.features["periods"] else "all"

    def test_func(self):
        """Return whether the reader may see P&L for the URL's bundle.

        :var url_path: address or bundle value found in URL
        :type url_path: str
        :return: Boolean
        """
        url_path = self.args[0].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        if not self.addresses or not self.manifest_test_func(len(self.addresses.split())):
            return False

        if self.features["linked_only"]:
            return all(
                is_linked_to_user(self.request.user, address)
                for address in self.addresses.split()
            )

        return True

    def handle_no_permission(self):
        """Explain the refusal and send the reader where it can be fixed.

        :var limit: number of addresses the reader's permission allows
        :type limit: int
        """
        try:
            return super().handle_no_permission()

        except PermissionDenied:
            if self.addresses and self.features["linked_only"]:
                messages.error(self.request, LINKED_ONLY_ERROR)
                return redirect("subscriptions")

            limit = addresses_limit_for_permission(
                self.manifest.required_permission, _permission(self.request.user)
            )
            if limit:
                messages.error(self.request, mark_safe(ADDRESSES_LIMIT_ERROR % (limit,)))
                return redirect("home")

            return redirect("subscriptions")

    def base_context(self):
        """Return the context every fragment of this widget needs.

        :return: dict
        """
        return {
            "query": urlencode({"currency": self.currency(), "period": self.period()}),
            "period": self.period(),
            "period_labels": PERIOD_LABELS,
            "path": self.args[0].upper(),
            "bundle": self.bundle,
            "addresses": self.addresses,
            "features": self.features,
            "currency": self.currency(),
        }


class PnlView(PnlAccessMixin, TemplateView):
    """Page holding the P&L widget; its body loads from :class:`PnlStatusView`.

    :var template_name: relative path to Django template's name for view
    :type template_name: str
    """

    template_name = "pnl/index.html"

    def get_context_data(self, *args, **kwargs):
        """Update context with the bundle, the tier's features and site name.

        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context.update(self.base_context())
        context["website_name"] = settings.WEBSITE_NAME
        return context


class PnlStatusView(PnlAccessMixin, View):
    """Fragment showing progress, a process button, or the P&L table."""

    def _progress(self, events):
        """Render processing progress from the engine's event records.

        :param events: bundle's phases and processing statuses
        :type events: dict
        :var update: processing status calculator shared with historic
        :type update: :class:`UpdateStatus`
        :return: :class:`django.http.HttpResponse`
        """
        update = UpdateStatus({"bundle": self.bundle, "addresses": self.addresses})
        context = {**self.base_context(), **update.template_context(events=events)}
        return render(self.request, "pnl/_progress.html", context)

    def get(self, request, *args, **kwargs):
        """Render the fragment matching the bundle's processing state.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var events: bundle's phases and processing statuses
        :type events: dict
        :var data: engine's P&L results or a show-update marker
        :type data: dict
        :var currency: denomination shown
        :type currency: str
        :return: :class:`django.http.HttpResponse`
        """
        events = _restore_event_phase_keys(
            _engine("pnl:events", "GET", self.bundle, "events/") or {}
        )
        if events and events.get(self.bundle, {}).get(-1, {}).get("state") != "finished":
            return self._progress(events)

        currency = self.currency()
        payload = {"currency": currency}
        start = period_start(self.period())
        if start is not None:
            payload["period_start"] = start

        data = _engine("pnl:evaluate", "POST", self.bundle, "evaluate/", json=payload)
        context = self.base_context()
        if not data or data.get("type") == "show_update":
            return render(request, "pnl/_process.html", context)

        context["summary"] = summary(data["totals"], currency)
        if data["totals"].get("period"):
            context["period_summary"] = period_summary(data["totals"]["period"], currency)
        context["rows"] = [table_row(row, currency) for row in data["assets"]]
        return render(request, "pnl/_table.html", context)


class PnlProcessView(PnlAccessMixin, View):
    """Start processing the bundle, within the reader's total address allowance."""

    def post(self, request, *args, **kwargs):
        """Record the bundle for the reader and ask the engine to process it.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var count: number of addresses in the bundle
        :type count: int
        :var allowed: addresses the reader's tier allows in total
        :type allowed: int
        :var used: addresses the reader keeps in other bundles
        :type used: int
        :return: :class:`django.http.HttpResponse`
        """
        count = len(self.addresses.split())
        allowed = addresses_limit_for_permission(
            self.manifest.required_permission, _permission(request.user)
        )
        used = addresses_in_use(request.user, exclude_bundle=self.bundle)
        if used + count > allowed:
            context = self.base_context()
            context["over_allowance"] = {"allowed": allowed, "used": used}
            context["kept"] = PnlBundle.objects.filter(user=request.user).exclude(
                bundle=self.bundle
            )
            return render(request, "pnl/_process.html", context)

        _engine(
            "pnl:process",
            "POST",
            self.bundle,
            "process/",
            json={"addresses": self.addresses},
        )
        PnlBundle.objects.update_or_create(
            user=request.user, bundle=self.bundle, defaults={"address_count": count}
        )
        return self._started()

    def _started(self):
        """Render empty progress that starts polling.

        :return: :class:`django.http.HttpResponse`
        """
        update = UpdateStatus({"bundle": self.bundle, "addresses": self.addresses})
        context = {**self.base_context(), **update.template_context()}
        return render(self.request, "pnl/_progress.html", context)


class PnlRemoveView(LoginRequiredMixin, View):
    """Drop a bundle from the reader's P&L, freeing its addresses."""

    def post(self, request, *args, **kwargs):
        """Forget the bundle for the reader; clear engine state once nobody keeps it.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var bundle: bundle hash
        :type bundle: str
        :return: :class:`django.http.HttpResponse`
        """
        bundle = args[0].upper()
        PnlBundle.objects.filter(user=request.user, bundle=bundle).delete()
        if not PnlBundle.objects.filter(bundle=bundle).exists():
            _engine("pnl:reset", "DELETE", bundle)

        return render(request, "pnl/_removed.html", {"bundle": bundle})


class PnlAssetView(PnlAccessMixin, View):
    """Fragment listing one asset's events, for tiers with the drill-down."""

    def get(self, request, *args, **kwargs):
        """Render the asset's acquisitions, disposals and income.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var data: engine's asset events
        :type data: dict
        :var currency: denomination shown
        :type currency: str
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["drilldown"]:
            raise Http404

        currency = self.currency()
        data = _engine(
            "pnl:asset",
            "POST",
            self.bundle,
            "asset/",
            json={"asset": args[1], "currency": currency},
        )
        if not data or data.get("type") == "show_update":
            raise Http404

        context = self.base_context()
        context["asset_label"] = asset_label(data)
        context["events"] = [
            event_row(event, data.get("decimals"), currency) for event in data["events"]
        ]
        return render(request, "pnl/_asset.html", context)


class PnlAlertView(PnlAccessMixin, View):
    """Create a price alert for an asset at a multiple of its average cost."""

    def post(self, request, *args, **kwargs):
        """Store the rule through the alerts widget's own form and confirm it.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var form: the alerts widget's rule form, which enforces the tier
        :type form: :class:`AlertRuleForm`
        :return: :class:`django.http.HttpResponse`
        """
        form = AlertRuleForm(
            data={
                "subject": Subject.ASA_PRICE,
                "direction": request.POST.get("direction"),
                "threshold": request.POST.get("threshold"),
                "asset_id": args[1],
                "threshold_unit": self.currency(),
                "asset_unit": request.POST.get("unit", "")[:32],
            },
            user=request.user,
            address=self.args[0].upper(),
        )
        context = self.base_context()
        if form.is_valid():
            context["rule"] = form.save()
        else:
            context["errors"] = [
                message for messages in form.errors.values() for message in messages
            ]

        return render(request, "pnl/_alert.html", context)
