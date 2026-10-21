"""Module containing the profit and loss widget's views."""

import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from algosdk.encoding import is_valid_address
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView, View

from api.client import BackendError, engine_request
from api.widgets import bundle_and_addresses_from_path
from utils.explorers import normalized_explorer
from utils.fiat import fiat_for_user
from walletauth.gating import is_linked_to_user
from widgethost.enforcement import WidgetAccessMixin
from widgethost.manifest import addresses_limit_for_permission
from widgets.inhouse.historic.consumers import _restore_event_phase_keys
from widgets.inhouse.alerts.forms import AlertRuleForm
from widgets.inhouse.alerts.models import Subject
from widgets.inhouse.historic.structs import UpdateStatus

from .display import (
    asset_label,
    chart,
    concentration,
    event_row,
    issues,
    period_summary,
    processed_iso,
    processed_time,
    reprocess_changes,
    summary,
    table_row,
    winners_and_losers,
)
from .export import events_csv, table_csv
from .forms import OVERRIDE_EVENT, PnlOverrideForm
from .manifest import MANIFEST
from .models import PnlBundle, PnlHiddenAsset, PnlOverride, PnlSettings
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
MORE_ROWS = {
    "unvalued": "held without a current price",
    "collapsed": "sold out or without a market",
    "hidden": "hidden by you",
}
#: Seconds a requested update may stay queued before the banner gives up waiting.
UPDATE_QUEUED_LIMIT = 1800
REPORT_EXPIRED_MESSAGE = (
    "That PDF report is no longer available; prepare it again below the table."
)
EXPORT_WAIT_MESSAGE = (
    "Profit and loss is still being worked out; download the CSV once the table shows."
)
EVENTS_WAIT_MESSAGE = (
    "The events are still being prepared; download them again in a minute."
)
#: Most overrides of each kind a reader may keep per bundle; the engine's limit.
OVERRIDES_LIMIT = 1000


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


def _explorer(user):
    """Return the reader's explorer key, the default one without a profile.

    :param user: request's user
    :type user: :class:`User`
    :return: str
    """
    try:
        return user.profile.preferred_explorer_or_default()
    except AttributeError:
        return normalized_explorer(None)


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
    # whole hours, so the engine's saved evaluation for the period is reused
    return now - now % 3600 - days * 86400 if days else None


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
        return features_for(_permission(self.request.user), fiat=self.fiat())

    def fiat(self):
        """Return the reader's fiat in lower case, "usd" when it has no rate.

        :return: str
        """
        return fiat_for_user(self.request.user)["code"].lower()

    def currency(self):
        """Return the requested denomination if the tier allows it, else the fiat.

        :var currencies: denominations the reader may choose, their fiat first
        :type currencies: tuple
        :return: str
        """
        currencies = self.features["currencies"]
        currency = self.request.GET.get("currency", currencies[0])
        return currency if currency in currencies else currencies[0]

    def period(self):
        """Return the requested period if the tier allows it, else all-time.

        :var period: requested period
        :type period: str
        :return: str
        """
        period = self.request.GET.get("period", "all")
        return period if period in self.features["periods"] else "all"

    def valuation(self):
        """Return the requested valuation if the tier allows it, else spot.

        :var valuation: requested valuation
        :type valuation: str
        :return: str
        """
        valuation = self.request.GET.get("valuation", "spot")
        return valuation if valuation in self.features["valuations"] else "spot"

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

    def cost_method(self):
        """Return the reader's saved cost basis method if the tier allows it.

        :var methods: cost basis methods the tier allows, the default first
        :type methods: tuple
        :var saved: the reader's saved settings, None without any
        :type saved: :class:`PnlSettings`
        :return: str
        """
        methods = self.features["cost_methods"]
        saved = getattr(self.request.user, "pnl_settings", None)
        method = saved.cost_method if saved else methods[0]
        return method if method in methods else methods[0]

    def count_nfts(self):
        """Return whether held NFTs are valued; only higher tiers may leave them out.

        :var saved: the reader's saved settings, None without any
        :type saved: :class:`PnlSettings`
        :return: Boolean
        """
        saved = getattr(self.request.user, "pnl_settings", None)
        return not (self.features["nft_choice"] and saved and not saved.count_nfts)

    def saved_overrides(self, kind):
        """Return the reader's overrides of `kind` for this bundle, none below the tier.

        :param kind: "basis" or "value"
        :type kind: str
        :return: :class:`django.db.models.QuerySet`
        """
        if not self.features["overrides"]:
            return PnlOverride.objects.none()

        return self.request.user.pnl_overrides.filter(
            bundle=self.bundle, kind=kind
        ).order_by("asset", "event")

    def overrides(self):
        """Return the reader's overrides as the engine reads them, None without any.

        :var payload: overrides keyed by the engine's kind names
        :type payload: dict
        :return: dict or None
        """
        payload = {
            "basis": [
                {
                    "id": override.event,
                    "asset": override.asset,
                    "amount": override.amount_text,
                    "currency": override.currency,
                }
                for override in self.saved_overrides("basis")
            ],
            "values": [
                {
                    "asset": override.asset,
                    "amount": override.amount_text,
                    "currency": override.currency,
                }
                for override in self.saved_overrides("value")
            ],
            "own": [override.event for override in self.saved_overrides("own")],
        }
        return {kind: entries for kind, entries in payload.items() if entries} or None

    def with_overrides(self, payload):
        """Return the engine request `payload` with the reader's overrides, if any.

        :param payload: engine request
        :type payload: dict
        :var overrides: see :meth:`overrides`
        :type overrides: dict or None
        :return: dict
        """
        overrides = self.overrides()
        return {**payload, "overrides": overrides} if overrides else payload

    def evaluate_payload(self):
        """Return the engine's evaluate request for the reader's switches.

        :var start: first second of the period, None for all-time
        :type start: int or None
        :return: dict
        """
        payload = {
            "currency": self.currency(),
            "valuation": self.valuation(),
            "method": self.cost_method(),
        }
        start = period_start(self.period())
        if start is not None:
            payload["period_start"] = start
        if not self.count_nfts():
            payload["nfts"] = False

        return self.with_overrides(payload)

    def reader_settings(self):
        """Return the reader's saved P&L settings, unsaved defaults without any.

        :return: :class:`PnlSettings`
        """
        return PnlSettings.objects.filter(user=self.request.user).first() or PnlSettings(
            user=self.request.user
        )

    def table_url(self):
        """Return the page's address on the table's tab, with the reader's switches.

        :return: str
        """
        return f"{reverse('pnl', args=[self.args[0]])}?{self.base_context()['query']}"

    def evaluation(self):
        """Return the engine's P&L results for the reader's switches.

        :return: dict or None
        """
        return _engine(
            "pnl:evaluate", "POST", self.bundle, "evaluate/", json=self.evaluate_payload()
        )

    def table_rows(self, data):
        """Return every asset of `data` formatted for the table, by row group.

        :param data: engine's P&L results
        :type data: dict
        :var hidden: ids of the assets the reader hid from this bundle's table
        :type hidden: set
        :var rows: formatted rows in the engine's order
        :type rows: list
        :var labels: asset labels by asset id
        :type labels: dict
        :return: dict
        """
        hidden = set(
            self.request.user.pnl_hidden_assets.filter(bundle=self.bundle).values_list(
                "asset", flat=True
            )
        )
        values = {override.asset: override for override in self.saved_overrides("value")}
        rows = [table_row(row, self.currency()) for row in data["assets"]]
        labels = {row["asset"]: row["label"] for row in rows}
        groups = {"open": [], **{group: [] for group in MORE_ROWS}}
        for row in rows:
            row["farm_paid_in"] = ", ".join(
                labels.get(asset, f"#{asset}") for asset in row["farm_assets"]
            )
            row["hidden"] = row["asset"] in hidden
            row["override"] = values.get(row["asset"])
            row["can_set_value"] = self.features["overrides"] and (
                row["held"] and (not row["valued"] or row["override"] is not None)
            )
            if row["hidden"]:
                groups["hidden"].append(row)
            elif not row["held"] or row["no_market"]:
                groups["collapsed"].append(row)
            elif not row["valued"]:
                groups["unvalued"].append(row)
            else:
                groups["open"].append(row)

        return groups

    def row_context(self):
        """Return the context a table row needs besides the row itself.

        :return: dict
        """
        return {
            **self.base_context(),
            "columns": 11 if self.features["lp_analytics"] else 10,
        }

    def base_context(self):
        """Return the context every fragment of this widget needs.

        :return: dict
        """
        return {
            "query": urlencode(
                {
                    "currency": self.currency(),
                    "period": self.period(),
                    "valuation": self.valuation(),
                }
            ),
            "period": self.period(),
            "valuation": self.valuation(),
            "period_labels": PERIOD_LABELS,
            "path": self.args[0].upper(),
            "bundle": self.bundle,
            "addresses": self.addresses,
            "features": self.features,
            "currency": self.currency(),
            "cost_method": self.cost_method(),
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
        if self.request.GET.get("tab") == "settings":
            context["tab"] = "settings"
            context["pnl_settings"] = self.reader_settings()
            context["wallets"] = self.saved_overrides("own")
        return context


class PnlStatusView(PnlAccessMixin, View):
    """Fragment showing progress, a process button, or the P&L table."""

    def _progress(self, events):
        """Render processing progress from the engine's event records.

        :param events: bundle's phases and processing statuses, None before any
        :type events: dict
        :var update: processing status calculator shared with historic
        :type update: :class:`UpdateStatus`
        :return: :class:`django.http.HttpResponse`
        """
        update = UpdateStatus({"bundle": self.bundle, "addresses": self.addresses})
        context = {**self.base_context(), **update.template_context(events=events)}
        return render(self.request, "pnl/_progress.html", context)

    def get(self, request, *args, **kwargs):
        """Render the bundle's state, or a retry offer when the engine fails.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :return: :class:`django.http.HttpResponse`
        """
        try:
            return self._state(request)

        except BackendError:
            return render(request, "pnl/_unavailable.html", self.base_context())

    def _state(self, request):
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
        running = (
            events and events.get(self.bundle, {}).get(-1, {}).get("state") != "finished"
        )
        currency = self.currency()
        data = self.evaluation()
        context = self.row_context()
        if running and not (data and "assets" in data):
            # without a table to keep showing, the run's own progress
            return self._progress(events)

        if data and data.get("type") == "processing":
            return self._progress(None)

        if data and data.get("type") == "pricing":
            context["pricing"] = {key: data.get(key) for key in ("done", "total")}
            return render(request, "pnl/_pricing.html", context)

        if data and data.get("type") == "valuing":
            return render(request, "pnl/_valuing.html", context)

        if data and data.get("type") == "evaluating":
            return render(request, "pnl/_evaluating.html", context)

        if not data or data.get("type") == "show_update":
            return render(request, "pnl/_process.html", context)

        context["summary"] = summary(data["totals"], currency)
        if data["totals"].get("period"):
            context["period_summary"] = period_summary(data["totals"]["period"], currency)
        groups = self.table_rows(data)
        context["rows"] = groups["open"]
        context["more"] = [
            (group, len(groups[group]), label) for group, label in MORE_ROWS.items()
        ]
        context["hidden_count"] = len(groups["hidden"])
        if self.features["winners"]:
            hidden = [row["asset"] for row in groups["hidden"]]
            context["winners"] = winners_and_losers(data["assets"], currency, hidden)
        if self.features["concentration"]:
            context["concentration"] = concentration(
                data["assets"], data["totals"], currency
            )
        context["issues"] = issues(data["assets"], currency)
        context["changes"] = reprocess_changes(
            data.get("changes"), data["assets"], currency
        )
        context["processed_at"] = processed_time(data.get("processed_at"))
        context["processed_iso"] = processed_iso(data.get("processed_at"))
        context["unapplied"] = sum(
            len(data["totals"].get(key, []))
            for key in ("unapplied_basis", "unapplied_values", "unapplied_own")
        )
        context["updating"] = data.get("updating")
        context["pricing"] = data.get("pricing") or {}
        return render(request, "pnl/_table.html", context)


class PnlUpdatingView(PnlAccessMixin, View):
    """Banner above the last table while the bundle is updated, polling itself."""

    def get(self, request, *args, **kwargs):
        """Render what is being updated, or the offer to show the new figures.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var since: seconds since epoch the reader asked for the update, 0 if not
        :type since: int
        :var data: engine's update state
        :type data: dict
        :var updating: what is being updated, None once done
        :type updating: str or None
        :return: :class:`django.http.HttpResponse`
        """
        try:
            since = int(request.GET.get("since", 0))
        except ValueError:
            since = 0

        context = self.base_context()
        context["since"] = since
        try:
            data = (
                _engine(
                    "pnl:events",
                    "POST",
                    self.bundle,
                    "updating/",
                    json=self.evaluate_payload(),
                )
                or {}
            )
        except BackendError:
            # keep polling: the engine may only be restarting
            context["updating"] = "unknown"
            return render(request, "pnl/_updating.html", context)

        updating = data.get("updating")
        if not updating and since and data.get("rows_at", 0) < since:
            # the queued run has not written its rows yet
            updating = (
                "queued" if time.time() - since < UPDATE_QUEUED_LIMIT else "stalled"
            )

        context["updating"] = updating
        context["pricing"] = data.get("pricing") or {}
        return render(request, "pnl/_updating.html", context)


class PnlRowsView(PnlAccessMixin, View):
    """Fragment with the table rows collapsed by default, or those the reader hid."""

    def get(self, request, *args, **kwargs):
        """Render the requested group's rows as a table body.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var group: "collapsed" or "hidden"
        :type group: str
        :var data: engine's P&L results or a state marker
        :type data: dict
        :return: :class:`django.http.HttpResponse`
        """
        group = request.GET.get("group")
        if group not in MORE_ROWS:
            raise Http404

        try:
            data = self.evaluation()
        except BackendError:
            raise Http404

        if not data or "assets" not in data:
            raise Http404

        context = self.row_context()
        context["rows"] = self.table_rows(data)[group]
        return render(request, "pnl/_rows.html", context)


class PnlHideView(PnlAccessMixin, View):
    """Hide an asset from the bundle's table, or show it again."""

    def post(self, request, *args, **kwargs):
        """Store the reader's choice and render what replaces the asset's row.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var asset: asset id as the engine names it
        :type asset: str
        :var data: engine's P&L results or a state marker
        :type data: dict
        :var groups: the bundle's formatted rows by row group
        :type groups: dict
        :var rows: the asset's formatted row, empty if the engine has none
        :type rows: list
        :return: :class:`django.http.HttpResponse`
        """
        asset = args[1]
        context = self.row_context()
        if request.POST.get("hidden") == "1":
            PnlHiddenAsset.objects.get_or_create(
                user=request.user, bundle=self.bundle, asset=asset
            )
            context["asset"] = asset
            context["label"] = request.POST.get("label", "")[:64] or f"#{asset}"
            return render(request, "pnl/_row_hidden.html", context)

        PnlHiddenAsset.objects.filter(
            user=request.user, bundle=self.bundle, asset=asset
        ).delete()
        try:
            data = self.evaluation()
        except BackendError:
            data = None

        groups = self.table_rows(data) if data and "assets" in data else {}
        rows = [
            row for group in groups.values() for row in group if row["asset"] == asset
        ]
        if not rows:
            raise Http404

        context["row"] = rows[0]
        return render(request, "pnl/_row.html", context)


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
        if request.GET.get("update"):
            # the table stays; its banner follows the run
            context = self.base_context()
            context["updating"] = "queued"
            context["since"] = int(time.time())
            return render(request, "pnl/_updating.html", context)

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


class PnlResetView(PnlAccessMixin, View):
    """Delete the bundle's engine data, historic's included, and offer processing."""

    def post(self, request, *args, **kwargs):
        """Reset the bundle in the engine from scratch and render the process button.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :return: :class:`django.http.HttpResponse`
        """
        try:
            _engine("pnl:reset", "DELETE", self.bundle, "?scratch=1")

        except BackendError:
            return render(request, "pnl/_unavailable.html", self.base_context())

        if request.GET.get("tab") == "settings":
            # the Settings tab has no #id-pnl-body: reload on the table's tab
            response = HttpResponse(status=204)
            response["HX-Redirect"] = self.table_url()
            return response

        return render(request, "pnl/_process.html", self.base_context())


class PnlSettingsView(PnlAccessMixin, View):
    """Save the reader's P&L settings from the Settings tab."""

    def post(self, request, *args, **kwargs):
        """Store a valid CSV separator and cost method and render the form again.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var reader_settings: the reader's P&L settings
        :type reader_settings: :class:`PnlSettings`
        :var separator: requested separator key
        :type separator: str
        :var method: requested cost basis method
        :type method: str
        :var page_format: requested PDF report page size
        :type page_format: str
        :var changed: whether a valid value was saved
        :type changed: Boolean
        :return: :class:`django.http.HttpResponse`
        """
        reader_settings = self.reader_settings()
        separator = request.POST.get("csv_separator")
        method = request.POST.get("cost_method")
        page_format = request.POST.get("page_format")
        changed = False
        if self.features["export"] and separator in PnlSettings.SEPARATORS:
            reader_settings.csv_separator = separator
            changed = True
        if method in self.features["cost_methods"]:
            reader_settings.cost_method = method
            changed = True
        if self.features["report"] and page_format in dict(
            PnlSettings.PAGE_FORMAT_CHOICES
        ):
            reader_settings.page_format = page_format
            changed = True
        if self.features["nft_choice"] and "count_nfts" in request.POST:
            # the form's hidden "0" comes first; a ticked box posts "1" after it
            reader_settings.count_nfts = request.POST.get("count_nfts") == "1"
            changed = True

        if changed:
            reader_settings.save()

        context = self.base_context()
        context["saved"] = changed
        context["pnl_settings"] = reader_settings
        return render(request, "pnl/_settings_form.html", context)


class PnlOverrideView(PnlAccessMixin, View):
    """Set or remove the reader's cost for a deposit, or value for an asset."""

    def post(self, request, *args, **kwargs):
        """Store the figure and send the page back to the table to re-evaluate.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var kind: "basis" or "value"
        :type kind: str
        :var event: the deposit's transaction or group id; empty for a value
        :type event: str
        :var lookup: fields naming the override
        :type lookup: dict
        :var form: the posted amount and currency
        :type form: :class:`PnlOverrideForm`
        :var response: empty answer redirecting the page
        :type response: :class:`django.http.HttpResponse`
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["overrides"]:
            raise Http404

        kind = request.POST.get("kind")
        event = request.POST.get("event", "") if kind == "basis" else ""
        if kind not in dict(PnlOverride.KIND_CHOICES) or (
            kind == "basis" and not OVERRIDE_EVENT.fullmatch(event)
        ):
            raise Http404

        lookup = {
            "user": request.user,
            "bundle": self.bundle,
            "kind": kind,
            "asset": args[1],
            "event": event,
        }
        if request.POST.get("remove") == "1":
            PnlOverride.objects.filter(**lookup).delete()
        else:
            form = PnlOverrideForm(request.POST, currencies=self.features["currencies"])
            existing = PnlOverride.objects.filter(**lookup).exists()
            count = PnlOverride.objects.filter(
                user=request.user, bundle=self.bundle, kind=kind
            ).count()
            if not form.is_valid() or (not existing and count >= OVERRIDES_LIMIT):
                errors = [
                    message for messages in form.errors.values() for message in messages
                ] or [f"At most {OVERRIDES_LIMIT} per bundle."]
                return render(request, "pnl/_override_error.html", {"errors": errors})

            PnlOverride.objects.update_or_create(
                **lookup,
                defaults={
                    "amount": form.cleaned_data["amount"],
                    "currency": form.cleaned_data["currency"],
                },
            )

        response = HttpResponse(status=204)
        response["HX-Redirect"] = self.table_url()
        return response


class PnlWalletsView(PnlAccessMixin, View):
    """Add or remove another wallet of the reader's, from the Settings tab."""

    def post(self, request, *args, **kwargs):
        """Store or remove the wallet and render the list again.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var address: the posted public Algorand address
        :type address: str
        :var lookup: fields naming the wallet
        :type lookup: dict
        :var error: why the address was not added
        :type error: str
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["overrides"]:
            raise Http404

        address = request.POST.get("address", "").strip().upper()
        lookup = {
            "user": request.user,
            "bundle": self.bundle,
            "kind": "own",
            "asset": "",
            "event": address,
        }
        error = ""
        if request.POST.get("remove") == "1":
            PnlOverride.objects.filter(**lookup).delete()
        elif not is_valid_address(address):
            error = "That is not an Algorand address."
        elif address in self.addresses.split():
            error = "That address is already in this bundle."
        elif (
            not PnlOverride.objects.filter(**lookup).exists()
            and self.saved_overrides("own").count() >= OVERRIDES_LIMIT
        ):
            error = f"At most {OVERRIDES_LIMIT} per bundle."
        else:
            PnlOverride.objects.get_or_create(
                **lookup, defaults={"amount": 0, "currency": ""}
            )

        context = self.base_context()
        context["wallets"] = self.saved_overrides("own")
        context["wallet_error"] = error
        return render(request, "pnl/_wallets.html", context)


class PnlExportView(PnlAccessMixin, View):
    """The P&L table as a CSV download, for tiers with the export."""

    def get(self, request, *args, **kwargs):
        """Return the saved evaluation as CSV, or back to the page while there is none.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var data: engine's P&L results or a state marker
        :type data: dict
        :var response: CSV attachment
        :type response: :class:`django.http.HttpResponse`
        :var filename: attachment's name: bundle, currency, valuation and date
        :type filename: str
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["export"]:
            raise Http404

        try:
            data = self.evaluation()
        except BackendError:
            data = None

        if not data or "assets" not in data:
            messages.info(request, EXPORT_WAIT_MESSAGE)
            return redirect(self.table_url())

        response = HttpResponse(
            table_csv(data, self.reader_settings().separator),
            content_type="text/csv; charset=utf-8",
        )
        filename = "pnl-{}-{}-{}-{}-{}.csv".format(
            self.bundle[:8].lower(),
            self.currency(),
            self.valuation(),
            self.cost_method(),
            datetime.now(UTC).strftime("%Y%m%d"),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PnlEventsExportView(PnlAccessMixin, View):
    """Every event of the bundle as a CSV download, for tiers with the export."""

    def get(self, request, *args, **kwargs):
        """Return the engine's events as CSV, or back to the table while they are made.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var data: engine's history or a state marker
        :type data: dict
        :var response: CSV attachment
        :type response: :class:`django.http.HttpResponse`
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["export"]:
            raise Http404

        try:
            data = _engine(
                "pnl:asset",
                "POST",
                self.bundle,
                "history/",
                json=self.with_overrides(
                    {"currency": self.currency(), "method": self.cost_method()}
                ),
            )
        except BackendError:
            data = None

        if not data or "events" not in data:
            messages.info(request, EVENTS_WAIT_MESSAGE)
            return redirect(self.table_url())

        response = HttpResponse(
            events_csv(data, self.reader_settings().separator),
            content_type="text/csv; charset=utf-8",
        )
        filename = "pnl-events-{}-{}-{}-{}.csv".format(
            self.bundle[:8].lower(),
            self.currency(),
            self.cost_method(),
            datetime.now(UTC).strftime("%Y%m%d"),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


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
            json=self.with_overrides(
                {"asset": args[1], "currency": currency, "method": self.cost_method()}
            ),
        )
        if not data or data.get("type") in ("show_update", "processing", "pricing"):
            raise Http404

        context = self.base_context()
        context["asset"] = args[1]
        context["asset_label"] = asset_label(data)
        costs = {
            override.event: override
            for override in self.saved_overrides("basis").filter(asset=args[1])
        }
        context["events"] = [
            event_row(event, data.get("decimals"), currency, _explorer(request.user))
            for event in data["events"]
        ]
        for event in context["events"]:
            event["override"] = costs.get(event["id"]) if event["deposit"] else None
        return render(request, "pnl/_asset.html", context)


class PnlChartView(PnlAccessMixin, View):
    """Fragment drawing cumulative P&L over time, for tiers with the chart."""

    def get(self, request, *args, **kwargs):
        """Render the chart, a polling placeholder while it is drawn, or nothing.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var data: engine's chart points or a state marker
        :type data: dict
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["chart"]:
            raise Http404

        context = self.base_context()
        try:
            data = _engine(
                "pnl:evaluate",
                "POST",
                self.bundle,
                "chart/",
                json=self.with_overrides({"currency": self.currency()}),
            )
        except BackendError:
            return render(request, "pnl/_chart_wait.html", {**context, "failed": True})

        if data and data.get("type") in ("charting", "processing", "pricing"):
            return render(request, "pnl/_chart_wait.html", context)

        context["chart"] = chart((data or {}).get("points"), self.currency())
        return render(request, "pnl/_chart.html", context)


class PnlAlertView(PnlAccessMixin, View):
    """Create a price alert for an asset at a multiple of its average cost."""

    def post(self, request, *args, **kwargs):
        """Store the rule through the alerts widget's own form and confirm it.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var direction: "up" or "down", from the clicked preset
        :type direction: str
        :var threshold: price per whole unit, from the clicked preset
        :type threshold: str
        :var form: the alerts widget's rule form, which enforces the tier
        :type form: :class:`AlertRuleForm`
        :return: :class:`django.http.HttpResponse`
        """
        direction, _, threshold = request.POST.get("preset", "").partition(" ")
        form = AlertRuleForm(
            data={
                "subject": Subject.ASA_PRICE,
                "direction": direction,
                "threshold": threshold,
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


class PnlReportView(PnlAccessMixin, View):
    """Ask the engine for the PDF report and show whether it is ready, polling."""

    def get(self, request, *args, **kwargs):
        """Render the report's state for the reader's switches and options.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var full: whether collapsed assets get full sections
        :type full: Boolean
        :var hidden: asset ids the reader hid from the table
        :type hidden: list
        :var data: engine's report state
        :type data: dict
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["report"]:
            raise Http404

        full = bool(request.GET.get("full") or request.POST.get("full"))
        hidden = sorted(
            request.user.pnl_hidden_assets.filter(bundle=self.bundle).values_list(
                "asset", flat=True
            )
        )
        context = self.base_context()
        context["full"] = full
        try:
            data = (
                _engine(
                    "pnl:evaluate",
                    "POST",
                    self.bundle,
                    "report/",
                    json={
                        **self.evaluate_payload(),
                        "page": self.reader_settings().page_format,
                        "full": full,
                        "hidden": hidden,
                    },
                )
                or {}
            )
        except BackendError:
            data = {"type": "failed"}

        context["report"] = data.get("type")
        context["key"] = data.get("key", "")
        return render(request, "pnl/_report.html", context)

    post = get


class PnlReportDownloadView(PnlAccessMixin, View):
    """The prepared PDF report as a download, for tiers with the report."""

    def get(self, request, *args, **kwargs):
        """Return the engine's saved report, or back to the table once it expired.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var engine_response: the engine's answer carrying the PDF
        :type engine_response: :class:`requests.Response`
        :var response: PDF attachment
        :type response: :class:`django.http.HttpResponse`
        :return: :class:`django.http.HttpResponse`
        """
        if not self.features["report"]:
            raise Http404

        try:
            engine_response = engine_request(
                "pnl:evaluate",
                "GET",
                f"/api/v2/pnl/{self.bundle}/report/",
                MANIFEST.engine_endpoints,
                params={"key": request.GET.get("key", "")},
            )
        except BackendError:
            messages.info(request, REPORT_EXPIRED_MESSAGE)
            return redirect(self.table_url())

        response = HttpResponse(engine_response.content, content_type="application/pdf")
        filename = "pnl-{}-{}-{}-{}-{}.pdf".format(
            self.bundle[:8].lower(),
            self.currency(),
            self.valuation(),
            self.cost_method(),
            datetime.now(UTC).strftime("%Y%m%d"),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
