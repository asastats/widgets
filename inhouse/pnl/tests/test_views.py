"""Testing module for :py:mod:`widgets.inhouse.pnl.views` module."""

import types

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from api.client import BackendError
from widgets.inhouse.pnl.models import PnlBundle
from widgets.inhouse.pnl.manifest import MANIFEST
from widgets.inhouse.alerts.models import AlertRule
from widgets.inhouse.pnl.views import (
    PnlAlertView,
    PnlAssetView,
    PnlChartView,
    PnlProcessView,
    PnlRemoveView,
    PnlStatusView,
    PnlView,
    _engine,
    addresses_in_use,
    period_start,
)

ASASTATSER = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]
CLUSTER = SUBSCRIPTION_TIER_PERMISSIONS["Cluster"]
BUNDLE = "B" * 40
ADDRESSES = "ADDRA ADDRB"


def _user(permission=0, user=None):
    if user is None:
        user = types.SimpleNamespace(is_authenticated=True)
        user.profile = types.SimpleNamespace(permission=permission)
        return user

    user.profile.permission = permission
    user.profile.save()
    return user


def _view(view_class, permission=0, query="", user=None, path=BUNDLE):
    view = view_class()
    view.request = RequestFactory().get(f"/pnl/{path}{query}")
    view.request.user = _user(permission, user)
    view.args = (path,)
    view.kwargs = {}
    view.bundle, view.addresses = BUNDLE, ADDRESSES
    return view


def _engine_results():
    return {
        "currency": "usd",
        "assets": [
            {
                "asset": "0",
                "lp": False,
                "name": "ALGO",
                "unit": "ALGO",
                "decimals": 6,
                "quantity": 5_000_000,
                "average_cost": 0.2,
                "price": 0.25,
                "value": 1_250_000,
                "cost": 1_000_000,
                "unrealized": 250_000,
                "realized": 0,
                "income": 0,
                "expenses": 0,
                "total": 250_000,
                "return": 0.25,
                "missing_quantity": 0,
                "unpriced": 0,
            }
        ],
        "totals": {"total": 250_000, "invested": 1_000_000, "unpriced_events": 2},
    }


class TestPnlViewsEngine:
    """Testing class for :py:func:`...pnl.views._engine`."""

    def test_pnl_views_engine_returns_json(self, mocker):
        request = mocker.patch("widgets.inhouse.pnl.views.engine_request")
        request.return_value.content = b"{}"
        returned = _engine("pnl:evaluate", "POST", BUNDLE, "evaluate/", json={"a": 1})
        assert returned == request.return_value.json.return_value
        request.assert_called_once_with(
            "pnl:evaluate",
            "POST",
            f"/api/v2/pnl/{BUNDLE}/evaluate/",
            MANIFEST.engine_endpoints,
            json={"a": 1},
        )

    def test_pnl_views_engine_returns_none_without_content(self, mocker):
        request = mocker.patch("widgets.inhouse.pnl.views.engine_request")
        request.return_value.content = b""
        assert _engine("pnl:reset", "DELETE", BUNDLE) is None
        assert request.call_args.args[2] == f"/api/v2/pnl/{BUNDLE}/"


class TestPnlViewsAccess:
    """Testing class for :py:class:`...pnl.views.PnlAccessMixin`."""

    def test_pnl_views_test_func_for_subscriber(self, mocker):
        view = _view(PnlView, ASASTATSER, path="abcd")
        mocker.patch(
            "widgets.inhouse.pnl.views.bundle_and_addresses_from_path",
            return_value=(BUNDLE, ADDRESSES),
        )
        gate = mocker.patch.object(PnlView, "manifest_test_func", return_value=True)
        linked = mocker.patch("widgets.inhouse.pnl.views.is_linked_to_user")
        assert view.test_func() is True
        gate.assert_called_once_with(2)
        linked.assert_not_called()

    @pytest.mark.parametrize("linked,expected", [([True], True), ([False], False)])
    def test_pnl_views_test_func_requires_linked_address_below_asastatser(
        self, mocker, linked, expected
    ):
        view = _view(PnlView, 0)
        mocker.patch(
            "widgets.inhouse.pnl.views.bundle_and_addresses_from_path",
            return_value=(BUNDLE, "ADDRA"),
        )
        mocker.patch.object(PnlView, "manifest_test_func", return_value=True)
        mocker.patch("widgets.inhouse.pnl.views.is_linked_to_user", side_effect=linked)
        assert view.test_func() is expected

    def test_pnl_views_test_func_fails_on_manifest_gate(self, mocker):
        view = _view(PnlView, CLUSTER)
        mocker.patch(
            "widgets.inhouse.pnl.views.bundle_and_addresses_from_path",
            return_value=(BUNDLE, None),
        )
        assert view.test_func() is False

    @pytest.mark.parametrize(
        "permission,limit,expected",
        [
            (0, 1, "subscriptions"),
            (ASASTATSER, 1, "home"),
            (ASASTATSER, 0, "subscriptions"),
        ],
    )
    def test_pnl_views_handle_no_permission(self, mocker, permission, limit, expected):
        view = _view(PnlView, permission)
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            side_effect=PermissionDenied,
        )
        mocker.patch(
            "widgets.inhouse.pnl.views.addresses_limit_for_permission",
            return_value=limit,
        )
        mocker.patch("widgets.inhouse.pnl.views.messages")
        mocker.patch("widgets.inhouse.pnl.views.redirect", side_effect=lambda name: name)
        assert view.handle_no_permission() == expected

    def test_pnl_views_currency_respects_tier(self):
        assert _view(PnlView, 0, "?currency=algo").currency() == "usd"
        assert _view(PnlView, ASASTATSER, "?currency=algo").currency() == "algo"
        assert _view(PnlView, ASASTATSER, "?currency=eur").currency() == "usd"

    def test_pnl_views_valuation_respects_tier(self):
        assert _view(PnlView, ASASTATSER, "?valuation=mve").valuation() == "spot"
        assert _view(PnlView, CLUSTER, "?valuation=mve").valuation() == "mve"
        assert _view(PnlView, CLUSTER, "?valuation=best").valuation() == "spot"

    def test_pnl_views_period_respects_tier(self):
        assert _view(PnlView, 0, "?period=7d").period() == "all"
        assert _view(PnlView, ASASTATSER, "?period=7d").period() == "7d"
        assert _view(PnlView, ASASTATSER, "?period=1y").period() == "all"

    def test_pnl_views_period_start(self):
        now = 1_700_000_000  # 14 Nov 2023
        assert period_start("all", now) is None
        assert period_start("7d", now) == now - 7 * 86400
        assert period_start("30d", now) == now - 30 * 86400
        assert period_start("ytd", now) == 1_672_531_200
        assert period_start("7d") is not None

    def test_pnl_views_page_context(self, mocker):
        mocker.patch(
            "django.views.generic.base.ContextMixin.get_context_data",
            return_value={},
        )
        context = _view(PnlView, ASASTATSER, path="abcd").get_context_data()
        assert context["path"] == "ABCD"
        assert context["bundle"] == BUNDLE
        assert context["features"]["drilldown"] is True
        assert "website_name" in context


class TestPnlViewsStatus:
    """Testing class for :py:class:`...pnl.views.PnlStatusView`."""

    def test_pnl_views_status_shows_progress_while_processing(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            return_value={"ADDRA": {"1": {"state": 5}}},
        )
        response = _view(PnlStatusView).get(None)
        assert b"<progress" in response.content
        assert b'hx-trigger="load delay:3s"' in response.content

    def test_pnl_views_status_offers_processing(self, mocker):
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "show_update"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Process" in response.content
        assert engine.call_args.kwargs == {
            "json": {"currency": "usd", "valuation": "spot"}
        }

    def test_pnl_views_status_renders_table_when_finished(self, mocker):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _engine_results()],
        )
        view = _view(PnlStatusView, ASASTATSER)
        response = view.get(view.request)
        assert b"+$0.25" in response.content
        assert b"2 events without a price" in response.content
        assert b'hx-get="/widgets/pnl/' in response.content
        assert b'hx-swap="innerHTML show:top"' in response.content
        assert b'data-label="Avg cost"' in response.content


class TestPnlViewsVsHold:
    """Testing class for the LP vs holding column."""

    @pytest.mark.parametrize("permission,shown", [(CLUSTER, True), (ASASTATSER, False)])
    def test_pnl_views_status_vs_holding_column_for_cluster(
        self, mocker, permission, shown
    ):
        results = _engine_results()
        results["assets"][0]["vs_hold"] = 3_000_000
        results["assets"][0]["fees"] = 4_000_000
        results["assets"][0]["divergence"] = -1_000_000
        results["assets"][0]["farm_income"] = 2_500_000
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, permission)
        content = view.get(view.request).content
        assert (b"vs holding" in content) is shown
        assert (b"+$3.00" in content) is shown
        assert (b"fees +$4.00 \xc2\xb7 divergence -$1.00" in content) is shown
        assert (b"farm yield $2.50" in content) is shown


class TestPnlViewsValuation:
    """Testing class for the MVE valuation switch and the illiquid flag."""

    @pytest.mark.parametrize("permission,shown", [(CLUSTER, True), (ASASTATSER, False)])
    def test_pnl_views_page_valuation_switch(self, permission, shown):
        view = _view(PnlView, permission, "?valuation=mve")
        response = view.get(view.request)
        response.render()
        assert (b'aria-label="Valuation"' in response.content) is shown
        assert (b"valuation=mve" in response.content) is shown

    def test_pnl_views_status_mve_and_illiquid(self, mocker):
        results = _engine_results()
        results["assets"][0]["illiquid"] = True
        results["totals"].update({"illiquid_assets": 1, "valuation": "mve"})
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, results]
        )
        view = _view(PnlStatusView, CLUSTER, "?valuation=mve")
        content = view.get(view.request).content
        assert engine.call_args.kwargs["json"]["valuation"] == "mve"
        assert b">illiquid</span>" in content
        assert b"1 holding marked" in content
        assert b"(MVE)" in content


class TestPnlViewsChart:
    """Testing class for the cumulative P&L chart fragment."""

    def test_pnl_views_chart_needs_professional(self):
        view = _view(PnlChartView, ASASTATSER)
        with pytest.raises(Http404):
            view.get(view.request)

    def test_pnl_views_chart_draws_points(self, mocker):
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            return_value={
                "points": [
                    {"date": 1_700_000_000, "pnl": 0.0},
                    {"date": 1_700_086_400, "pnl": 3_000_000.0},
                ]
            },
        )
        view = _view(PnlChartView, CLUSTER, "?currency=algo")
        response = view.get(view.request)
        assert engine.call_args.args[:4] == ("pnl:evaluate", "POST", BUNDLE, "chart/")
        assert engine.call_args.kwargs == {"json": {"currency": "algo"}}
        assert b'class="pnl-chart-line"' in response.content
        assert b"+3.00 ALGO" in response.content

    @pytest.mark.parametrize("state", ["charting", "pricing"])
    def test_pnl_views_chart_polls_while_drawn(self, mocker, state):
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value={"type": state})
        view = _view(PnlChartView, CLUSTER)
        content = view.get(view.request).content
        assert b'hx-trigger="load delay:5s" hx-target="#id-pnl-chart"' in content

    @pytest.mark.parametrize("data", [None, {"type": "show_update"}, {"points": []}])
    def test_pnl_views_chart_renders_nothing_without_points(self, mocker, data):
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=data)
        view = _view(PnlChartView, CLUSTER)
        assert view.get(view.request).content.strip() == b""

    def test_pnl_views_chart_when_engine_fails(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=BackendError("timed out")
        )
        view = _view(PnlChartView, CLUSTER)
        content = view.get(view.request).content
        assert b"chart could not be loaded" in content
        assert b"hx-trigger" not in content

    @pytest.mark.parametrize("permission,shown", [(CLUSTER, True), (ASASTATSER, False)])
    def test_pnl_views_table_loads_chart_for_professional(
        self, mocker, permission, shown
    ):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _engine_results()],
        )
        view = _view(PnlStatusView, permission)
        content = view.get(view.request).content
        assert (b'id="id-pnl-chart"' in content) is shown


class TestPnlViewsStatusValuing:
    """Testing class for the status view while the engine computes MVE."""

    def test_pnl_views_status_shows_valuing_and_keeps_polling(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "valuing"}],
        )
        view = _view(PnlStatusView, CLUSTER, "?valuation=mve")
        response = view.get(view.request)
        assert b"what selling each holding would fetch" in response.content
        assert b'hx-trigger="load delay:5s"' in response.content
        assert b"valuation=mve" in response.content


class TestPnlViewsStatusUnavailable:
    """Testing class for the status view when the engine fails or times out."""

    def test_pnl_views_status_offers_retry_when_engine_fails(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=BackendError("could not reach the backend: timed out"),
        )
        view = _view(PnlStatusView, ASASTATSER)
        response = view.get(view.request)
        assert response.status_code == 200
        assert b"could not be loaded just now" in response.content
        assert b'hx-target="#id-pnl-body">Retry</button>' in response.content


class TestPnlViewsStatusPricing:
    """Testing class for the status view while the engine prices rows."""

    def test_pnl_views_status_shows_pricing_and_keeps_polling(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "pricing"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Pricing every transaction" in response.content
        assert b'hx-trigger="load delay:5s"' in response.content

    def test_pnl_views_asset_while_pricing(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value={"type": "pricing"}
        )
        view = _view(PnlAssetView, ASASTATSER)
        with pytest.raises(Http404):
            view.get(view.request, BUNDLE, "5")


class TestPnlViewsStatusPeriod:
    """Testing class for the status view's period."""

    def test_pnl_views_status_sends_period_and_renders_its_card(self, mocker):
        results = _engine_results()
        results["totals"]["period"] = {
            "pnl": 3_000_000,
            "return": 0.5,
            "start_value": 6_000_000,
            "end_value": 9_000_000,
            "net_flows": 0,
            "unvalued_assets": 0,
        }
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, results],
        )
        view = _view(PnlStatusView, ASASTATSER, "?period=30d")
        response = view.get(view.request)
        assert "period_start" in engine.call_args.kwargs["json"]
        assert b"30 days" in response.content
        assert b"+$3.00" in response.content
        assert b"period=30d" in response.content


@pytest.mark.django_db
class TestPnlViewsProcessAndRemove:
    """Testing class for processing allowance and bundle removal."""

    def test_pnl_views_addresses_in_use(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        PnlBundle.objects.create(user=user, bundle="X" * 40, address_count=3)
        PnlBundle.objects.create(user=user, bundle=BUNDLE, address_count=2)
        assert addresses_in_use(user) == 5
        assert addresses_in_use(user, exclude_bundle=BUNDLE) == 3

    def test_pnl_views_process_refuses_over_total_allowance(
        self, django_user_model, mocker
    ):
        user = django_user_model.objects.create(username="reader")
        PnlBundle.objects.create(user=user, bundle="X" * 40, address_count=4)
        engine = mocker.patch("widgets.inhouse.pnl.views._engine")
        view = _view(
            PnlProcessView, SUBSCRIPTION_TIER_PERMISSIONS["Professional"], user=user
        )
        response = view.post(view.request)
        assert b"allows profit and loss for 5 addresses" in response.content
        assert b"XXXX" in response.content
        engine.assert_not_called()
        assert not PnlBundle.objects.filter(bundle=BUNDLE).exists()

    def test_pnl_views_process_starts_and_records_bundle(self, django_user_model, mocker):
        user = django_user_model.objects.create(username="reader")
        engine = mocker.patch("widgets.inhouse.pnl.views._engine")
        view = _view(PnlProcessView, CLUSTER, user=user)
        response = view.post(view.request)
        engine.assert_called_once_with(
            "pnl:process", "POST", BUNDLE, "process/", json={"addresses": ADDRESSES}
        )
        assert PnlBundle.objects.get(user=user, bundle=BUNDLE).address_count == 2
        assert b"<progress" in response.content

    def test_pnl_views_remove_resets_engine_only_when_nobody_keeps_it(
        self, django_user_model, mocker
    ):
        first = django_user_model.objects.create(username="first")
        second = django_user_model.objects.create(username="second")
        PnlBundle.objects.create(user=first, bundle=BUNDLE, address_count=2)
        PnlBundle.objects.create(user=second, bundle=BUNDLE, address_count=2)
        engine = mocker.patch("widgets.inhouse.pnl.views._engine")
        request = RequestFactory().post("/")
        request.user = first
        response = PnlRemoveView().post(request, BUNDLE.lower())
        assert b"Removed" in response.content
        engine.assert_not_called()
        request.user = second
        PnlRemoveView().post(request, BUNDLE)
        engine.assert_called_once_with("pnl:reset", "DELETE", BUNDLE)
        assert not PnlBundle.objects.exists()


@pytest.mark.django_db
class TestPnlViewsAlert:
    """Testing class for :py:class:`...pnl.views.PnlAlertView`."""

    def _post(self, user, permission, data, query=""):
        view = _view(
            PnlAlertView, permission, query, user=user, path="ADDRA" * 11 + "ABC"
        )
        view.request = RequestFactory().post(f"/{query}", data)
        view.request.user = user
        return view.post(view.request, view.args[0], "31566704")

    def test_pnl_views_alert_creates_price_rule(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        response = self._post(
            user,
            ASASTATSER,
            {"direction": "up", "threshold": "1.25", "unit": "USDC"},
            "?currency=algo",
        )
        rule = AlertRule.objects.get(user=user)
        assert (rule.subject, rule.direction, rule.asset_id) == (
            "asa_price",
            "up",
            31566704,
        )
        assert (str(rule.threshold.normalize()), rule.threshold_unit) == ("1.25", "algo")
        assert rule.asset_unit == "USDC"
        assert b"Alert set: rises above 1.25 ALGO" in response.content
        assert b"Manage alerts" in response.content

    def test_pnl_views_alert_reports_the_alert_widgets_refusal(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        for _ in range(2):
            self._post(user, 0, {"direction": "up", "threshold": "1"})
        response = self._post(user, 0, {"direction": "up", "threshold": "1"})
        assert AlertRule.objects.filter(user=user).count() == 2
        assert b"pnl-warning" in response.content
        assert b"Alert set" not in response.content


class TestPnlViewsAsset:
    """Testing class for :py:class:`...pnl.views.PnlAssetView`."""

    def test_pnl_views_asset_needs_drilldown(self):
        view = _view(PnlAssetView, 0)
        with pytest.raises(Http404):
            view.get(view.request, BUNDLE, "5")

    def test_pnl_views_asset_without_processing(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value={"type": "show_update"}
        )
        view = _view(PnlAssetView, ASASTATSER)
        with pytest.raises(Http404):
            view.get(view.request, BUNDLE, "5")

    def test_pnl_views_asset_renders_events(self, mocker):
        data = {
            "asset": "5",
            "unit": "FIV",
            "decimals": 0,
            "events": [
                {
                    "date": 1_700_000_000,
                    "id": "TX",
                    "asset": "5",
                    "kind": "income",
                    "quantity": 3,
                    "value": 2_000_000,
                    "cost": 2_000_000,
                    "realized": None,
                    "description": "CyberSkulls staking reward",
                }
            ],
        }
        engine = mocker.patch("widgets.inhouse.pnl.views._engine", return_value=data)
        view = _view(PnlAssetView, ASASTATSER, "?currency=algo")
        response = view.get(view.request, BUNDLE, "5")
        assert b"Income" in response.content
        assert b'class="pnl-event-note">CyberSkulls staking reward' in response.content
        assert b"2.00 ALGO" in response.content
        assert engine.call_args.kwargs == {"json": {"asset": "5", "currency": "algo"}}


class TestPnlUrls:
    """Testing class for the widget's URL configuration."""

    @pytest.mark.parametrize(
        "suffix,view_class",
        [
            ("", PnlView),
            ("/status", PnlStatusView),
            ("/process", PnlProcessView),
            ("/remove", PnlRemoveView),
            ("/asset/LP123", PnlAssetView),
            ("/alert/31566704", PnlAlertView),
        ],
    )
    def test_pnl_urls_resolve(self, suffix, view_class):
        assert resolve(f"/widgets/pnl/{BUNDLE}{suffix}").func.view_class is view_class
