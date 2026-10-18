"""Testing module for :py:mod:`widgets.inhouse.pnl.views` module."""

import types

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from api.client import BackendError
from widgets.inhouse.pnl.models import PnlBundle, PnlHiddenAsset, PnlSettings
from widgets.inhouse.pnl.manifest import MANIFEST
from widgets.inhouse.alerts.models import AlertRule
from widgets.inhouse.pnl.views import (
    PnlAlertView,
    PnlAssetView,
    PnlChartView,
    PnlExportView,
    PnlHideView,
    PnlProcessView,
    PnlRemoveView,
    PnlResetView,
    PnlRowsView,
    PnlSettingsView,
    PnlStatusView,
    PnlView,
    _engine,
    addresses_in_use,
    period_start,
)

ASASTATSER = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]
CLUSTER = SUBSCRIPTION_TIER_PERMISSIONS["Cluster"]
PROFESSIONAL = SUBSCRIPTION_TIER_PERMISSIONS["Professional"]
BUNDLE = "B" * 40
ADDRESSES = "ADDRA ADDRB"


def _user(permission=0, user=None):
    if user is None:
        user = types.SimpleNamespace(is_authenticated=True)
        user.profile = types.SimpleNamespace(permission=permission)
        user.pnl_hidden_assets = PnlHiddenAsset.objects.none()
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

    def test_pnl_views_test_func_any_address_for_intro(self, mocker):
        view = _view(PnlView, SUBSCRIPTION_TIER_PERMISSIONS["Intro"])
        mocker.patch(
            "widgets.inhouse.pnl.views.bundle_and_addresses_from_path",
            return_value=(BUNDLE, "ADDRA"),
        )
        mocker.patch.object(PnlView, "manifest_test_func", return_value=True)
        linked = mocker.patch("widgets.inhouse.pnl.views.is_linked_to_user")
        assert view.test_func() is True
        linked.assert_not_called()

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

    def test_pnl_views_currency_for_a_eur_reader(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views.fiat_for_user",
            return_value={"code": "EUR", "rate": 0.9, "symbol": "€"},
        )
        # below Asastatser their fiat is the one currency, in place of USD
        assert _view(PnlView, 0).currency() == "eur"
        assert _view(PnlView, 0, "?currency=usd").currency() == "eur"
        assert _view(PnlView, ASASTATSER).features["currencies"] == ("eur", "algo")
        assert _view(PnlView, ASASTATSER, "?currency=algo").currency() == "algo"
        assert _view(PnlView, ASASTATSER, "?currency=usd").currency() == "eur"

    def test_pnl_views_fiat_is_the_readers(self, mocker):
        mocked = mocker.patch(
            "widgets.inhouse.pnl.views.fiat_for_user",
            return_value={"code": "USD", "rate": 1.0, "symbol": "$"},
        )
        view = _view(PnlView, 0)
        assert view.fiat() == "usd"
        mocked.assert_called_once_with(view.request.user)

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
        hour = now - now % 3600
        assert period_start("7d", now) == hour - 7 * 86400
        assert period_start("30d", now) == hour - 30 * 86400
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
        assert b"Start from scratch" not in response.content

    def test_pnl_views_status_offers_processing(self, mocker):
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "show_update"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Process" in response.content
        assert engine.call_args.kwargs == {
            "json": {"currency": "usd", "valuation": "spot", "method": "average"}
        }

    def test_pnl_views_status_renders_table_when_finished(self, mocker):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        results = _engine_results()
        results["assets"][0]["unpriced"] = 2
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, results],
        )
        view = _view(PnlStatusView, ASASTATSER)
        response = view.get(view.request)
        assert b"+$0.25" in response.content
        assert b"2 events without a price" in response.content
        assert b'hx-get="/widgets/pnl/' in response.content
        assert b'hx-swap="innerHTML show:top"' in response.content
        assert b'data-label="Avg cost"' in response.content
        assert b"Show the affected assets" in response.content
        assert b"Events without a price (1)" in response.content
        assert b'data-label="Issue">2 events<' in response.content


class TestPnlViewsVsHold:
    """Testing class for the LP vs holding column."""

    @pytest.mark.parametrize(
        "permission,shown", [(CLUSTER, True), (PROFESSIONAL, True), (ASASTATSER, False)]
    )
    def test_pnl_views_status_vs_holding_column_for_professional_and_up(
        self, mocker, permission, shown
    ):
        results = _engine_results()
        results["assets"][0]["vs_hold"] = 3_000_000
        results["assets"][0]["fees"] = 4_000_000
        results["assets"][0]["divergence"] = -1_000_000
        results["assets"][0]["farm_income"] = 2_500_000
        results["assets"][0]["farm_assets"] = ["0", "777"]
        results["assets"][0]["farm_unpriced"] = 1
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, permission)
        content = view.get(view.request).content
        assert (b"vs holding" in content) is shown
        assert (b"+$3.00" in content) is shown
        assert (b"fees +$4.00 \xc2\xb7 divergence -$1.00" in content) is shown
        assert (b"farm yield $2.50, 1 without a price" in content) is shown
        assert (b"in ALGO, #777: open those assets" in content) is shown


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

    @pytest.mark.parametrize("state", ["charting", "processing", "pricing"])
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

    def test_pnl_views_status_shows_progress_until_processing_starts(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "processing"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"<progress" in response.content
        assert b'value="0"' in response.content
        assert b'hx-trigger="load delay:3s"' in response.content

    def test_pnl_views_status_shows_evaluating_and_keeps_polling(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "evaluating"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Working out profit and loss" in response.content
        assert b'hx-trigger="load delay:5s"' in response.content

    def test_pnl_views_status_shows_pricing_and_keeps_polling(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "pricing"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Pricing every transaction" in response.content
        assert b'hx-trigger="load delay:3s"' in response.content
        assert b"<progress" not in response.content

    @pytest.mark.parametrize(
        "done,text",
        [(3, b"3 of 8 assets priced"), (8, b"All 8 assets priced, finishing")],
    )
    def test_pnl_views_status_shows_pricing_progress(self, mocker, done, text):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "pricing", "done": done, "total": 8}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert text in response.content
        assert f'<progress max="8" value="{done}">'.encode() in response.content

    @pytest.mark.parametrize("state", ["processing", "pricing"])
    def test_pnl_views_asset_while_pricing(self, mocker, state):
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value={"type": state})
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
class TestPnlViewsReset:
    """Testing class for :py:class:`...pnl.views.PnlResetView`."""

    def test_pnl_views_reset_starts_from_scratch_and_offers_processing(self, mocker):
        engine = mocker.patch("widgets.inhouse.pnl.views._engine")
        view = _view(PnlResetView, ASASTATSER)
        response = view.post(view.request, BUNDLE)
        engine.assert_called_once_with("pnl:reset", "DELETE", BUNDLE, "?scratch=1")
        assert b"/process?" in response.content

    def test_pnl_views_reset_for_engine_failure(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=BackendError("down")
        )
        view = _view(PnlResetView, ASASTATSER)
        response = view.post(view.request, BUNDLE)
        assert b"could not be loaded" in response.content


    def test_pnl_views_reset_from_settings_reloads_the_table(self, mocker):
        mocker.patch("widgets.inhouse.pnl.views._engine")
        view = _view(PnlResetView, ASASTATSER, query="?tab=settings")
        response = view.post(view.request, BUNDLE)
        assert response.status_code == 204
        assert response["HX-Redirect"] == (
            f"/widgets/pnl/{BUNDLE}?currency=usd&period=all&valuation=spot"
        )


@pytest.mark.django_db
class TestPnlViewsSettings:
    """Testing class for the Settings tab and :py:class:`...pnl.views.PnlSettingsView`."""

    def _post(self, permission, user, data):
        view = _view(PnlSettingsView, permission, user=user)
        view.request = RequestFactory().post(f"/pnl/{BUNDLE}/settings", data)
        view.request.user = user
        return view.post(view.request, BUNDLE)

    def test_pnl_views_settings_tab_context(self, mocker, django_user_model):
        mocker.patch(
            "django.views.generic.base.ContextMixin.get_context_data",
            side_effect=lambda *args, **kwargs: {},
        )
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        context = _view(PnlView, CLUSTER, query="?tab=settings", user=user).get_context_data()
        assert context["tab"] == "settings"
        assert context["pnl_settings"].csv_separator == "comma"
        assert context["pnl_settings"].pk is None
        assert "tab" not in _view(PnlView, CLUSTER, user=user).get_context_data()

    def test_pnl_views_settings_saves_the_separator(self, django_user_model):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        response = self._post(CLUSTER, user, {"csv_separator": "semicolon"})
        assert PnlSettings.objects.get(user=user).separator == ";"
        assert b"Saved." in response.content
        assert b'value="semicolon" selected' in response.content
        self._post(CLUSTER, user, {"csv_separator": "tab"})
        assert PnlSettings.objects.get(user=user).separator == "\t"
        assert PnlSettings.objects.count() == 1

    @pytest.mark.parametrize(
        "permission,separator",
        [(CLUSTER, "pipe"), (CLUSTER, None), (ASASTATSER, "semicolon")],
    )
    def test_pnl_views_settings_refuses(self, django_user_model, permission, separator):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        data = {"csv_separator": separator} if separator else {}
        response = self._post(permission, user, data)
        assert not PnlSettings.objects.exists()
        assert b"Saved." not in response.content

    def test_pnl_views_settings_saves_the_cost_method(self, django_user_model):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        response = self._post(CLUSTER, user, {"cost_method": "fifo"})
        assert PnlSettings.objects.get(user=user).cost_method == "fifo"
        assert PnlSettings.objects.get(user=user).csv_separator == "comma"
        assert b"Saved." in response.content
        assert b"Cost basis" in response.content
        assert b'value="fifo" selected' in response.content

    def test_pnl_views_settings_refuses_fifo_below_cluster(self, django_user_model):
        user = _user(PROFESSIONAL, django_user_model.objects.create(username="reader"))
        response = self._post(PROFESSIONAL, user, {"cost_method": "fifo"})
        assert not PnlSettings.objects.exists()
        assert b"Saved." not in response.content


@pytest.mark.django_db
class TestPnlViewsCostMethod:
    """Testing class for the reader's saved cost basis method in engine requests."""

    def _reader(self, django_user_model, permission, method="fifo"):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        PnlSettings.objects.create(user=user, cost_method=method)
        return user

    @pytest.mark.parametrize(
        "permission,expected", [(CLUSTER, "fifo"), (PROFESSIONAL, "average")]
    )
    def test_pnl_views_status_sends_the_saved_method(
        self, mocker, django_user_model, permission, expected
    ):
        user = self._reader(django_user_model, permission)
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, _engine_results()]
        )
        view = _view(PnlStatusView, permission, user=user)
        content = view.get(view.request).content
        assert engine.call_args.kwargs["json"]["method"] == expected
        assert (b"First in, first out" in content) is (expected == "fifo")
        assert (b"Average cost per asset." in content) is (expected == "average")

    def test_pnl_views_asset_sends_the_saved_method(self, mocker, django_user_model):
        user = self._reader(django_user_model, CLUSTER)
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            return_value={"asset": "5", "name": "Five", "decimals": 0, "events": []},
        )
        view = _view(PnlAssetView, CLUSTER, user=user)
        view.get(view.request, BUNDLE, "5")
        assert engine.call_args.kwargs["json"]["method"] == "fifo"

    def test_pnl_views_export_names_the_method(self, mocker, django_user_model):
        user = self._reader(django_user_model, CLUSTER)
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=_engine_results())
        view = _view(PnlExportView, CLUSTER, user=user)
        response = view.get(view.request, BUNDLE)
        assert 'filename="pnl-bbbbbbbb-usd-spot-fifo-' in response["Content-Disposition"]


@pytest.mark.django_db
class TestPnlViewsExport:
    """Testing class for :py:class:`...pnl.views.PnlExportView`."""

    def test_pnl_views_export_needs_cluster(self, django_user_model):
        user = _user(ASASTATSER, django_user_model.objects.create(username="reader"))
        view = _view(PnlExportView, ASASTATSER, user=user)
        with pytest.raises(Http404):
            view.get(view.request, BUNDLE)

    def test_pnl_views_export_returns_the_saved_table(self, mocker, django_user_model):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        PnlSettings.objects.create(user=user, csv_separator="semicolon")
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value=_engine_results()
        )
        view = _view(PnlExportView, CLUSTER, query="?currency=algo&period=7d", user=user)
        response = view.get(view.request, BUNDLE)
        assert engine.call_args.args == ("pnl:evaluate", "POST", BUNDLE, "evaluate/")
        assert engine.call_args.kwargs["json"]["currency"] == "algo"
        assert "period_start" in engine.call_args.kwargs["json"]
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"].startswith(
            'attachment; filename="pnl-bbbbbbbb-algo-spot-'
        )
        lines = response.content.decode("utf-8-sig").splitlines()
        assert lines[0].startswith("Asset ID;Asset;Name;")
        assert lines[1].startswith("0;ALGO;ALGO;5.000000;")
        assert lines[2].startswith(";Total;")

    @pytest.mark.parametrize(
        "engine",
        [{"return_value": {"type": "evaluating"}}, {"return_value": None},
         {"side_effect": BackendError("down")}],
    )
    def test_pnl_views_export_back_to_the_page_until_ready(
        self, mocker, django_user_model, engine
    ):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        mocker.patch("widgets.inhouse.pnl.views._engine", **engine)
        info = mocker.patch("widgets.inhouse.pnl.views.messages.info")
        view = _view(PnlExportView, CLUSTER, user=user)
        response = view.get(view.request, BUNDLE)
        assert response.status_code == 302
        assert response.url == f"/widgets/pnl/{BUNDLE}?currency=usd&period=all&valuation=spot"
        info.assert_called_once()

    @pytest.mark.parametrize("permission,shown", [(CLUSTER, True), (ASASTATSER, False)])
    def test_pnl_views_table_offers_the_csv_to_cluster(self, mocker, permission, shown):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _engine_results()],
        )
        view = _view(PnlStatusView, permission)
        response = view.get(view.request)
        assert (b"/export?" in response.content) is shown
        assert b"Start from scratch" not in response.content


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
        assert engine.call_args.kwargs == {
            "json": {"asset": "5", "currency": "algo", "method": "average"}
        }


def _grouped_results():
    results = _engine_results()
    held = results["assets"][0]
    results["assets"] += [
        {**held, "asset": "5", "name": "Sold", "unit": "SOLD", "quantity": 0},
        {**held, "asset": "6", "name": "Spam", "unit": "SPAM", "no_market": True},
        {**held, "asset": "7", "name": "Muted", "unit": "MUTE"},
    ]
    return results


class TestPnlViewsRowGroups:
    """Testing class for the table's collapsed and hidden rows."""

    def test_pnl_views_status_collapses_closed_and_hidden_rows(
        self, mocker, django_user_model
    ):
        user = django_user_model.objects.create(username="reader")
        PnlHiddenAsset.objects.create(user=user, bundle=BUNDLE, asset="7")
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _grouped_results()],
        )
        view = _view(PnlStatusView, ASASTATSER, user=user)
        response = view.get(view.request)
        assert b">ALGO</button>" in response.content
        assert b"SOLD" not in response.content
        assert b"SPAM" not in response.content
        assert b"MUTE" not in response.content
        assert b"Show 2 more: sold out or without a market" in response.content
        assert b"Show 1 hidden by you" in response.content
        assert b"group=collapsed" in response.content
        assert b"group=hidden" in response.content
        assert b'colspan="10"' in response.content
        assert b"Assets you hide still count in the totals." in response.content

    def test_pnl_views_status_without_rows_to_collapse(self, mocker):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _engine_results()],
        )
        view = _view(PnlStatusView, PROFESSIONAL)
        response = view.get(view.request)
        assert b"pnl-more-cell" not in response.content
        assert b"still count in the totals" not in response.content

    def test_pnl_views_rows_needs_a_known_group(self):
        view = _view(PnlRowsView, query="?group=all")
        with pytest.raises(Http404):
            view.get(view.request)

    def test_pnl_views_rows_when_the_engine_fails(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=BackendError("down")
        )
        view = _view(PnlRowsView, query="?group=collapsed")
        with pytest.raises(Http404):
            view.get(view.request)

    def test_pnl_views_rows_without_results(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value={"type": "pricing"}
        )
        view = _view(PnlRowsView, query="?group=collapsed")
        with pytest.raises(Http404):
            view.get(view.request)

    def test_pnl_views_rows_renders_the_collapsed_group(self, mocker):
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=_grouped_results())
        view = _view(PnlRowsView, PROFESSIONAL, query="?group=collapsed")
        response = view.get(view.request)
        assert response.content.strip().startswith(b"<tbody>")
        assert b"SOLD" in response.content
        assert b"SPAM" in response.content
        assert b"MUTE" not in response.content
        assert b">ALGO<" not in response.content
        assert response.content.count(b'class="pnl-closed"') == 2
        assert b">Hide</button>" in response.content

    def test_pnl_views_rows_renders_the_hidden_group(self, mocker, django_user_model):
        user = django_user_model.objects.create(username="reader")
        PnlHiddenAsset.objects.create(user=user, bundle=BUNDLE, asset="7")
        PnlHiddenAsset.objects.create(user=user, bundle="C" * 40, asset="5")
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=_grouped_results())
        view = _view(PnlRowsView, query="?group=hidden", user=user)
        response = view.get(view.request)
        assert b"MUTE" in response.content
        assert b"SOLD" not in response.content
        assert b">Show again</button>" in response.content
        assert b'name="hidden" value="0"' in response.content


class TestPnlViewsHide:
    """Testing class for :py:class:`...pnl.views.PnlHideView`."""

    def _post(self, user, data, asset="7"):
        view = _view(PnlHideView, user=user)
        view.request = RequestFactory().post("/", data)
        view.request.user = user
        return view.post(view.request, BUNDLE, asset)

    def test_pnl_views_hide_stores_the_asset_once(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        for _ in range(2):
            response = self._post(user, {"hidden": "1", "label": "MUTE"})
        assert list(
            PnlHiddenAsset.objects.filter(user=user).values_list("bundle", "asset")
        ) == [(BUNDLE, "7")]
        assert b"MUTE is hidden; it still counts in the totals." in response.content
        assert b">Undo</button>" in response.content
        assert b'colspan="10"' in response.content

    def test_pnl_views_hide_without_a_label(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        response = self._post(user, {"hidden": "1"})
        assert b"#7 is hidden" in response.content

    def test_pnl_views_hide_shows_the_asset_again(self, mocker, django_user_model):
        user = django_user_model.objects.create(username="reader")
        PnlHiddenAsset.objects.create(user=user, bundle=BUNDLE, asset="7")
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=_grouped_results())
        response = self._post(user, {"hidden": "0"})
        assert not PnlHiddenAsset.objects.filter(user=user).exists()
        assert response.content.strip().startswith(b"<tr>")
        assert b"MUTE" in response.content
        assert b">Hide</button>" in response.content

    def test_pnl_views_hide_shows_again_an_asset_the_engine_lacks(
        self, mocker, django_user_model
    ):
        user = django_user_model.objects.create(username="reader")
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=_grouped_results())
        with pytest.raises(Http404):
            self._post(user, {"hidden": "0"}, asset="99")

    def test_pnl_views_hide_shows_again_when_the_engine_fails(
        self, mocker, django_user_model
    ):
        user = django_user_model.objects.create(username="reader")
        PnlHiddenAsset.objects.create(user=user, bundle=BUNDLE, asset="7")
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=BackendError("down")
        )
        with pytest.raises(Http404):
            self._post(user, {"hidden": "0"})
        assert not PnlHiddenAsset.objects.filter(user=user).exists()


class TestPnlUrls:
    """Testing class for the widget's URL configuration."""

    @pytest.mark.parametrize(
        "suffix,view_class",
        [
            ("", PnlView),
            ("/status", PnlStatusView),
            ("/process", PnlProcessView),
            ("/remove", PnlRemoveView),
            ("/reset", PnlResetView),
            ("/asset/LP123", PnlAssetView),
            ("/rows", PnlRowsView),
            ("/hide/31566704", PnlHideView),
            ("/alert/31566704", PnlAlertView),
            ("/settings", PnlSettingsView),
            ("/export", PnlExportView),
        ],
    )
    def test_pnl_urls_resolve(self, suffix, view_class):
        assert resolve(f"/widgets/pnl/{BUNDLE}{suffix}").func.view_class is view_class
