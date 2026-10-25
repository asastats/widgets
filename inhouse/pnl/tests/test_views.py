"""Testing module for :py:mod:`widgets.inhouse.pnl.views` module."""

import types

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from api.client import BackendError
from widgets.inhouse.pnl.models import (
    PnlBundle,
    PnlHiddenAsset,
    PnlOverride,
    PnlSettings,
)
from widgets.inhouse.pnl.manifest import MANIFEST
from widgets.inhouse.alerts.models import AlertRule
from widgets.inhouse.pnl.views import (
    PnlAlertView,
    PnlAssetView,
    PnlChartView,
    PnlEventsExportView,
    PnlExportView,
    PnlHideView,
    PnlOverrideView,
    PnlProcessView,
    PnlRemoveView,
    PnlReportDownloadView,
    PnlReportView,
    PnlResetView,
    PnlRowsView,
    PnlSettingsView,
    PnlStatusView,
    PnlUpdatingView,
    PnlView,
    PnlWalletsView,
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
        user.pnl_overrides = PnlOverride.objects.none()
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

    def test_pnl_views_status_appraised_nfts(self, mocker):
        results = _engine_results()
        results["assets"][0]["nft"] = True
        results["totals"]["nft_value"] = 4_000_000
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, CLUSTER)
        content = view.get(view.request).content
        assert b">appraised</span>" in content
        assert b"$4.00 of the value is NFTs marked" in content

    def test_pnl_views_status_shows_what_a_reprocess_changed(self, mocker):
        results = _engine_results()
        results["changes"] = {
            "since": 1_760_000_000,
            "assets_changed": 1,
            "cost": -2_000_000,
            "realized": 0.0,
            "income": 0.0,
            "expenses": 0.0,
            "assets": [
                {
                    "asset": "0",
                    "quantity": 0.0,
                    "cost": -2_000_000,
                    "realized": 0.0,
                    "income": 0.0,
                    "expenses": 0.0,
                }
            ],
        }
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, ASASTATSER)
        content = view.get(view.request).content
        assert b"What changed when the history was processed again: 1 asset" in content
        assert (
            b'Transactions from before <time datetime="2025-10-09T08:53:20Z" '
            b"data-local-time>9 Oct 2025, 08:53 UTC</time>," in content
        )

    @pytest.mark.parametrize(
        "permission,winners,concentration",
        [(0, False, False), (ASASTATSER, True, False), (PROFESSIONAL, True, True)],
    )
    def test_pnl_views_status_insights_by_tier(
        self, mocker, permission, winners, concentration
    ):
        results = _engine_results()
        results["totals"]["value"] = 1_250_000
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, permission)
        content = view.get(view.request).content
        assert (b"Winners and losers" in content) is winners
        assert (b"Concentration" in content) is concentration
        if concentration:
            assert b"make up 100.0% of the current value" not in content
            assert b"makes up 100.0% of the current value" in content

    def test_pnl_views_status_nfts_left_out(self, mocker):
        results = _engine_results()
        results["totals"]["nfts"] = False
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch("widgets.inhouse.pnl.views._engine", side_effect=[events, results])
        view = _view(PnlStatusView, CLUSTER)
        content = view.get(view.request).content
        assert b"NFTs are not valued, as chosen in Settings" in content
        assert b'href="/methodology/">How these figures are made' in content


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

    def test_pnl_views_process_update_keeps_the_table(self, django_user_model, mocker):
        user = django_user_model.objects.create(username="reader")
        mocker.patch("widgets.inhouse.pnl.views._engine")
        mocker.patch("widgets.inhouse.pnl.views.time.time", return_value=5_000.9)
        view = _view(PnlProcessView, CLUSTER, query="?update=1", user=user)
        response = view.post(view.request)
        assert b"<progress" not in response.content
        assert b'id="id-pnl-updating"' in response.content
        assert b"waiting for its turn" in response.content
        assert b"since=5000" in response.content

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

    @pytest.mark.parametrize("permission,tab", [(CLUSTER, "download"), (ASASTATSER, None)])
    def test_pnl_views_download_tab_context(
        self, mocker, django_user_model, permission, tab
    ):
        mocker.patch(
            "django.views.generic.base.ContextMixin.get_context_data",
            side_effect=lambda *args, **kwargs: {},
        )
        user = _user(permission, django_user_model.objects.create(username="reader"))
        view = _view(PnlView, permission, query="?tab=download", user=user)
        assert view.get_context_data().get("tab") == tab

    @pytest.mark.parametrize("permission,shown", [(CLUSTER, True), (ASASTATSER, False)])
    def test_pnl_views_download_tab_offers_the_files_to_cluster(
        self, django_user_model, permission, shown
    ):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        view = _view(PnlView, permission, query="?tab=download", user=user)
        response = view.get(view.request)
        response.render()
        assert (b">Download</a>" in response.content) is shown
        assert (b"/export?" in response.content) is shown
        assert (b"/events.csv?" in response.content) is shown
        assert (b'id="id-pnl-report"' in response.content) is shown
        assert (b'id="id-pnl-body"' in response.content) is not shown

    @pytest.mark.parametrize(
        "permission,shown", [(PROFESSIONAL, True), (ASASTATSER, False)]
    )
    def test_pnl_views_settings_tab_offers_the_nft_choice(
        self, django_user_model, permission, shown
    ):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        view = _view(PnlView, permission, query="?tab=settings", user=user)
        response = view.get(view.request)
        response.render()
        assert (b'name="count_nfts"' in response.content) is shown

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

    @pytest.mark.parametrize(
        "permission,saved", [(CLUSTER, "letter"), (PROFESSIONAL, "a4")]
    )
    def test_pnl_views_settings_saves_the_page_format(
        self, django_user_model, permission, saved
    ):
        user = django_user_model.objects.create(username="reader")
        response = self._post(permission, user, {"page_format": "letter"})
        reader_settings = PnlSettings.objects.filter(user=user).first()
        assert (reader_settings.page_format if reader_settings else "a4") == saved
        assert (b"PDF report" in response.content) is (permission == CLUSTER)

    @pytest.mark.parametrize(
        "permission,posted,saved",
        [
            (PROFESSIONAL, ["0"], False),
            (PROFESSIONAL, ["0", "1"], True),
            (ASASTATSER, ["0"], True),
        ],
    )
    def test_pnl_views_settings_saves_the_nft_choice(
        self, django_user_model, permission, posted, saved
    ):
        user = django_user_model.objects.create(username="reader")
        response = self._post(permission, user, {"count_nfts": posted})
        reader_settings = PnlSettings.objects.filter(user=user).first()
        assert (reader_settings.count_nfts if reader_settings else True) is saved
        assert (b'name="count_nfts"' in response.content) is (permission != ASASTATSER)

    def test_pnl_views_settings_other_fields_keep_the_nft_choice(self, django_user_model):
        user = django_user_model.objects.create(username="reader")
        PnlSettings.objects.create(user=user, count_nfts=False)
        self._post(CLUSTER, user, {"csv_separator": "tab"})
        assert PnlSettings.objects.get(user=user).count_nfts is False

    @pytest.mark.parametrize(
        "permission,count_nfts,sent",
        [
            (PROFESSIONAL, False, False),
            (PROFESSIONAL, True, None),
            (ASASTATSER, False, None),
        ],
    )
    def test_pnl_views_evaluate_payload_nfts(
        self, django_user_model, permission, count_nfts, sent
    ):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        PnlSettings.objects.create(user=user, count_nfts=count_nfts)
        payload = _view(PnlStatusView, permission, user=user).evaluate_payload()
        assert payload.get("nfts") is sent

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

    def test_pnl_views_status_explains_lifo(self, mocker, django_user_model):
        user = self._reader(django_user_model, CLUSTER, method="lifo")
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, _engine_results()]
        )
        view = _view(PnlStatusView, CLUSTER, user=user)
        content = view.get(view.request).content
        assert engine.call_args.kwargs["json"]["method"] == "lifo"
        assert b"Last in, first out" in content

    def test_pnl_views_status_explains_hifo(self, mocker, django_user_model):
        user = self._reader(django_user_model, CLUSTER, method="hifo")
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, _engine_results()]
        )
        view = _view(PnlStatusView, CLUSTER, user=user)
        content = view.get(view.request).content
        assert engine.call_args.kwargs["json"]["method"] == "hifo"
        assert b"Highest cost out first" in content

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
        assert response.url == (
            f"/widgets/pnl/{BUNDLE}?currency=usd&period=all&valuation=spot&tab=download"
        )
        info.assert_called_once()

    def test_pnl_views_events_export_needs_cluster(self, django_user_model):
        user = _user(ASASTATSER, django_user_model.objects.create(username="reader"))
        view = _view(PnlEventsExportView, ASASTATSER, user=user)
        with pytest.raises(Http404):
            view.get(view.request, BUNDLE)

    def test_pnl_views_events_export_returns_every_event(self, mocker, django_user_model):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        PnlSettings.objects.create(user=user, csv_separator="tab", cost_method="fifo")
        history = {
            "currency": "eur",
            "assets": {"5": {"asset": "5", "unit": "FIV", "decimals": 0}},
            "events": [
                {
                    "date": 1_700_000_000,
                    "id": "G",
                    "asset": "5",
                    "kind": "swap",
                    "quantity": 2,
                    "value": 3_000_000,
                    "cost": 1_000_000,
                    "realized": 2_000_000,
                    "rate": 0.9,
                }
            ],
        }
        engine = mocker.patch("widgets.inhouse.pnl.views._engine", return_value=history)
        view = _view(PnlEventsExportView, CLUSTER, user=user)
        response = view.get(view.request, BUNDLE)
        assert engine.call_args.args == ("pnl:asset", "POST", BUNDLE, "history/")
        assert engine.call_args.kwargs["json"]["method"] == "fifo"
        assert response["Content-Disposition"].startswith(
            'attachment; filename="pnl-events-bbbbbbbb-usd-fifo-'
        )
        lines = response.content.decode("utf-8-sig").splitlines()
        assert lines[0].startswith("Date (UTC)\tTransaction ID\t")
        assert lines[1].split("\t")[:4] == ["2023-11-14 22:13:20", "G", "5", "FIV"]

    @pytest.mark.parametrize(
        "engine",
        [
            {"return_value": {"type": "evaluating"}},
            {"return_value": None},
            {"side_effect": BackendError("down")},
        ],
    )
    def test_pnl_views_events_export_back_to_the_page_until_ready(
        self, mocker, django_user_model, engine
    ):
        user = _user(CLUSTER, django_user_model.objects.create(username="reader"))
        mocker.patch("widgets.inhouse.pnl.views._engine", **engine)
        info = mocker.patch("widgets.inhouse.pnl.views.messages.info")
        view = _view(PnlEventsExportView, CLUSTER, user=user)
        response = view.get(view.request, BUNDLE)
        assert response.status_code == 302
        assert response.url.endswith("&tab=download")
        info.assert_called_once()

    @pytest.mark.parametrize("permission", [CLUSTER, ASASTATSER])
    def test_pnl_views_table_leaves_the_csv_to_the_download_tab(self, mocker, permission):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[events, _engine_results()],
        )
        view = _view(PnlStatusView, permission)
        response = view.get(view.request)
        assert b"/export?" not in response.content
        assert b"/events.csv?" not in response.content
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
            {"preset": "up 1.25", "unit": "USDC"},
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
            self._post(user, 0, {"preset": "up 1"})
        response = self._post(user, 0, {"preset": "up 1"})
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
        assert b'href="https://allo.info/tx/group/TX"' in response.content

    def test_pnl_views_asset_links_to_the_readers_explorer(
        self, mocker, django_user_model
    ):
        user = _user(ASASTATSER, django_user_model.objects.create(username="reader"))
        user.profile.preferred_explorer = "pera"
        user.profile.save()
        event = {
            "date": 1,
            "id": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "asset": "5",
            "kind": "swap",
            "quantity": 1,
            "value": 1,
            "cost": 1,
            "realized": None,
        }
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            return_value={"asset": "5", "decimals": 0, "events": [event]},
        )
        view = _view(PnlAssetView, ASASTATSER, user=user)
        response = view.get(view.request, BUNDLE, "5")
        link = b'href="https://explorer.perawallet.app/tx/%s"' % (b"A" * 52)
        assert link in response.content


def _grouped_results():
    results = _engine_results()
    held = results["assets"][0]
    results["assets"] += [
        {**held, "asset": "5", "name": "Sold", "unit": "SOLD", "quantity": 0},
        {**held, "asset": "6", "name": "Spam", "unit": "SPAM", "no_market": True},
        {**held, "asset": "7", "name": "Muted", "unit": "MUTE"},
        {**held, "asset": "8", "name": "Unpriced", "unit": "NOPR", "value": None},
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
        # a sold-out asset may be among the winners, never in the table's rows
        assert b"SOLD" not in response.content.split(b"pnl-table-wrap")[1]
        assert b"SPAM" not in response.content
        assert b"MUTE" not in response.content
        assert b"NOPR" not in response.content.split(b"pnl-table-wrap")[1]
        assert b"Show 2 sold out or without a market" in response.content
        assert b"Show 1 held without a current price" in response.content
        assert b"group=unvalued" in response.content
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

    def test_pnl_views_rows_renders_the_unvalued_group(self, mocker):
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value=_grouped_results()
        )
        view = _view(PnlRowsView, query="?group=unvalued")
        response = view.get(view.request)
        assert b"NOPR" in response.content
        assert b"SOLD" not in response.content

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


class TestPnlViewsUpdating:
    """Testing class for the table kept during an update and its banner."""

    def _status(self, mocker, results, finished=True):
        events = {BUNDLE: {"-1": {"state": "finished" if finished else 5}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, results]
        )
        view = _view(PnlStatusView, ASASTATSER)
        return view.get(view.request)

    def test_pnl_views_status_offers_the_update(self, mocker):
        results = {**_engine_results(), "processed_at": 1_760_000_000}
        response = self._status(mocker, results)
        assert (
            b'Transactions processed <time datetime="2025-10-09T08:53:20Z" '
            b"data-local-time>9 Oct 2025, 08:53 UTC</time>." in response.content
        )
        assert b">Update</button>" in response.content
        assert b"update=1" in response.content
        assert b'class="pnl-updating"' not in response.content

    def test_pnl_views_status_keeps_the_table_while_processing(self, mocker):
        results = {
            **_engine_results(),
            "processed_at": 1_760_000_000,
            "updating": "processing",
        }
        response = self._status(mocker, results, finished=False)
        assert b"<progress" not in response.content
        assert b'data-label="Avg cost"' in response.content
        assert b"Updating: processing new transactions." in response.content
        assert b"The figures below are from transactions processed" in response.content
        assert b">Update</button>" not in response.content
        assert b'hx-trigger="load delay:5s"' in response.content

    def test_pnl_views_status_banner_shows_pricing_progress(self, mocker):
        results = {
            **_engine_results(),
            "updating": "pricing",
            "pricing": {"done": 3, "total": 8},
        }
        response = self._status(mocker, results)
        assert b"pricing new transactions (3 of 8 assets)" in response.content

    def _banner(self, mocker, query="", **engine):
        mocker.patch("widgets.inhouse.pnl.views.time.time", return_value=10_000)
        call = mocker.patch("widgets.inhouse.pnl.views._engine", **engine)
        view = _view(PnlUpdatingView, ASASTATSER, query=query)
        return view.get(view.request), call

    def test_pnl_views_updating_asks_the_engine(self, mocker):
        response, call = self._banner(
            mocker, return_value={"updating": "evaluating", "rows_at": 1}
        )
        assert call.call_args.args == ("pnl:events", "POST", BUNDLE, "updating/")
        assert call.call_args.kwargs == {
            "json": {"currency": "usd", "valuation": "spot", "method": "average"}
        }
        assert b"working out the new figures" in response.content
        assert b"since=0" in response.content

    def test_pnl_views_updating_when_the_engine_fails(self, mocker):
        response, _ = self._banner(mocker, side_effect=BackendError("down"))
        assert b"cannot be read right now" in response.content
        assert b'hx-trigger="load delay:5s"' in response.content

    @pytest.mark.parametrize(
        "query,engine,expected",
        [
            ("?since=9000", {"updating": None, "rows_at": 8_000}, b"waiting for its turn"),
            ("?since=5000", {"updating": None, "rows_at": 4_000}, b"has not started yet"),
            ("?since=9000", {"updating": None, "rows_at": 9_500}, b"New figures are ready"),
            ("?since=soon", {"updating": None, "rows_at": 1}, b"New figures are ready"),
            ("", None, b"New figures are ready"),
        ],
    )
    def test_pnl_views_updating_states(self, mocker, query, engine, expected):
        response, _ = self._banner(mocker, query, return_value=engine)
        assert expected in response.content

    def test_pnl_views_updating_offers_the_new_figures_without_polling(self, mocker):
        response, _ = self._banner(mocker, return_value={"updating": None})
        assert b'hx-target="#id-pnl-body"' in response.content
        assert b"load delay" not in response.content

    def test_pnl_views_updating_stops_polling_once_stalled(self, mocker):
        response, _ = self._banner(
            mocker, "?since=5000", return_value={"updating": None, "rows_at": 1}
        )
        assert b"hx-get" not in response.content


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
            ("/updating", PnlUpdatingView),
            ("/report", PnlReportView),
            ("/report/download", PnlReportDownloadView),
            ("/hide/31566704", PnlHideView),
            ("/alert/31566704", PnlAlertView),
            ("/settings", PnlSettingsView),
            ("/export", PnlExportView),
        ],
    )
    def test_pnl_urls_resolve(self, suffix, view_class):
        assert resolve(f"/widgets/pnl/{BUNDLE}{suffix}").func.view_class is view_class


@pytest.mark.django_db
class TestPnlViewsReport:
    """Testing class for the PDF report's preparation and download."""

    def _report(self, mocker, django_user_model, permission=CLUSTER, **engine):
        user = _user(permission, django_user_model.objects.create(username="reader"))
        PnlHiddenAsset.objects.create(user=user, bundle=BUNDLE, asset="7")
        PnlSettings.objects.create(user=user, page_format="letter")
        call = mocker.patch("widgets.inhouse.pnl.views._engine", **engine)
        view = _view(PnlReportView, permission, user=user)
        view.request = RequestFactory().post(f"/pnl/{BUNDLE}/report", {"full": "1"})
        view.request.user = user
        return view, call

    def test_pnl_views_report_needs_cluster(self, mocker, django_user_model):
        view, _ = self._report(mocker, django_user_model, PROFESSIONAL)
        with pytest.raises(Http404):
            view.post(view.request)

    def test_pnl_views_report_asks_the_engine(self, mocker, django_user_model):
        view, call = self._report(
            mocker, django_user_model, return_value={"type": "preparing", "key": "k"}
        )
        response = view.post(view.request)
        assert call.call_args.args == ("pnl:evaluate", "POST", BUNDLE, "report/")
        assert call.call_args.kwargs["json"] == {
            "currency": "usd",
            "valuation": "spot",
            "method": "average",
            "page": "letter",
            "full": True,
            "hidden": ["7"],
        }
        assert b"Preparing the PDF report with every asset in full" in response.content
        assert b'hx-trigger="load delay:4s"' in response.content
        assert b"full=1" in response.content

    def test_pnl_views_report_ready(self, mocker, django_user_model):
        view, _ = self._report(
            mocker, django_user_model, return_value={"type": "ready", "key": "k_a4"}
        )
        response = view.get(view.request)
        assert b"Download PDF report" in response.content
        assert b"data-app-download>Download PDF report" in response.content
        assert b"key=k_a4" in response.content
        assert b"load delay" not in response.content

    @pytest.mark.parametrize(
        "engine,expected",
        [
            ({"side_effect": BackendError("down")}, b"could not be prepared"),
            ({"return_value": {"type": "pricing"}}, b"being updated"),
            ({"return_value": None}, b"Prepare PDF report"),
        ],
    )
    def test_pnl_views_report_states(self, mocker, django_user_model, engine, expected):
        view, _ = self._report(mocker, django_user_model, **engine)
        response = view.post(view.request)
        assert expected in response.content

    def test_pnl_views_table_leaves_the_report_to_the_download_tab(self, mocker):
        events = {BUNDLE: {"-1": {"state": "finished"}}}
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", side_effect=[events, _engine_results()]
        )
        view = _view(PnlStatusView, CLUSTER)
        content = view.get(view.request).content
        assert b'id="id-pnl-report"' not in content
        assert b"Prepare PDF report" not in content

    def _download(self, mocker, permission=CLUSTER, **engine):
        call = mocker.patch("widgets.inhouse.pnl.views.engine_request", **engine)
        view = _view(PnlReportDownloadView, permission, query="?key=k_a4")
        view.request._messages = mocker.MagicMock()
        return view, call

    def test_pnl_views_report_download_needs_cluster(self, mocker):
        view, _ = self._download(mocker, PROFESSIONAL)
        with pytest.raises(Http404):
            view.get(view.request)

    def test_pnl_views_report_download(self, mocker):
        view, call = self._download(
            mocker, return_value=types.SimpleNamespace(content=b"%PDF-1.7")
        )
        clock = mocker.patch("widgets.inhouse.pnl.views.datetime")
        clock.now.return_value.strftime.return_value = "20261018"
        response = view.get(view.request)
        assert response.content == b"%PDF-1.7"
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == (
            'attachment; filename="pnl-bbbbbbbb-usd-spot-average-20261018.pdf"'
        )
        assert call.call_args.args[:3] == (
            "pnl:evaluate",
            "GET",
            f"/api/v2/pnl/{BUNDLE}/report/",
        )
        assert call.call_args.kwargs == {"params": {"key": "k_a4"}}

    def test_pnl_views_report_download_after_it_expired(self, mocker):
        view, _ = self._download(mocker, side_effect=BackendError("404: gone"))
        response = view.get(view.request)
        assert response.status_code == 302
        assert response.url.startswith(f"/widgets/pnl/{BUNDLE}?")
        assert response.url.endswith("&tab=download")


def _override(user, kind="value", asset="8", event="", amount="2.5", currency="usd"):
    return PnlOverride.objects.create(
        user=user,
        bundle=BUNDLE,
        kind=kind,
        asset=asset,
        event=event,
        amount=amount,
        currency=currency,
    )


def _deposit_events():
    return {
        "asset": "8",
        "unit": "NOPR",
        "decimals": 0,
        "events": [
            {
                "date": 1_700_000_000,
                "id": "DEP/1+=",
                "asset": "8",
                "kind": "deposit",
                "quantity": 10,
                "value": None,
                "cost": 0,
                "realized": None,
            },
            {
                "date": 1_700_000_100,
                "id": "SWAP",
                "asset": "8",
                "kind": "swap",
                "quantity": -2,
                "value": 1_000_000,
                "cost": 0,
                "realized": 1_000_000,
            },
        ],
    }


@pytest.mark.django_db
class TestPnlViewsOverrides:
    """Testing class for :py:class:`...pnl.views.PnlOverrideView` and its payloads."""

    def _reader(self, django_user_model, permission=ASASTATSER):
        return _user(permission, django_user_model.objects.create(username="reader"))

    def _post(self, user, data, asset="8", permission=ASASTATSER):
        view = _view(PnlOverrideView, permission, user=user)
        view.request = RequestFactory().post("/", data)
        view.request.user = user
        return view.post(view.request, BUNDLE, asset)

    def test_pnl_views_override_value_saved_changed_and_removed(
        self, django_user_model
    ):
        user = self._reader(django_user_model)
        response = self._post(user, {"kind": "value", "amount": "2.50", "currency": "usd"})
        assert response.status_code == 204
        assert f"/pnl/{BUNDLE}?currency=usd" in response["HX-Redirect"]
        self._post(user, {"kind": "value", "amount": "3", "currency": "algo"})
        saved = PnlOverride.objects.get(user=user)
        assert (saved.kind, saved.asset, saved.event) == ("value", "8", "")
        assert (saved.amount_text, saved.currency) == ("3", "algo")
        self._post(user, {"kind": "value", "remove": "1"})
        assert not PnlOverride.objects.exists()

    def test_pnl_views_override_basis_needs_an_event(self, django_user_model):
        user = self._reader(django_user_model)
        for event in ("", "a b", "x" * 65):
            with pytest.raises(Http404):
                self._post(
                    user,
                    {"kind": "basis", "event": event, "amount": "1", "currency": "usd"},
                )
        self._post(
            user, {"kind": "basis", "event": "DEP/1+=", "amount": "50", "currency": "usd"}
        )
        assert PnlOverride.objects.get().event == "DEP/1+="

    @pytest.mark.parametrize(
        "permission,kind",
        [(SUBSCRIPTION_TIER_PERMISSIONS["Intro"], "value"), (ASASTATSER, "other")],
    )
    def test_pnl_views_override_refused(self, django_user_model, permission, kind):
        user = self._reader(django_user_model, permission)
        with pytest.raises(Http404):
            self._post(
                user,
                {"kind": kind, "amount": "1", "currency": "usd"},
                permission=permission,
            )

    @pytest.mark.parametrize(
        "data",
        [
            {"amount": "-1", "currency": "usd"},
            {"amount": "many", "currency": "usd"},
            {"amount": "1", "currency": "eur"},
        ],
    )
    def test_pnl_views_override_invalid(self, django_user_model, data):
        user = self._reader(django_user_model)
        response = self._post(user, {"kind": "value", **data})
        assert b'class="pnl-override-error"' in response.content
        assert not PnlOverride.objects.exists()

    def test_pnl_views_override_limit(self, django_user_model, mocker):
        user = self._reader(django_user_model)
        mocker.patch("widgets.inhouse.pnl.views.OVERRIDES_LIMIT", 1)
        _override(user, asset="7")
        response = self._post(user, {"kind": "value", "amount": "1", "currency": "usd"})
        assert b"At most 1 per bundle." in response.content
        response = self._post(
            user, {"kind": "value", "amount": "1", "currency": "usd"}, asset="7"
        )
        assert response.status_code == 204

    def test_pnl_views_override_payloads(self, django_user_model, mocker):
        user = self._reader(django_user_model)
        _override(user, kind="basis", event="DEP", amount="50.500", currency="usd")
        _override(user)
        PnlOverride.objects.create(
            user=user, bundle="C" * 40, kind="value", asset="9", amount=1, currency="usd"
        )
        view = _view(PnlStatusView, ASASTATSER, user=user)
        expected = {
            "basis": [{"id": "DEP", "asset": "8", "amount": "50.5", "currency": "usd"}],
            "values": [{"asset": "8", "amount": "2.5", "currency": "usd"}],
        }
        assert view.evaluate_payload()["overrides"] == expected
        assert view.overrides() == expected
        engine = mocker.patch("widgets.inhouse.pnl.views._engine", return_value={})
        mocker.patch("widgets.inhouse.pnl.views.messages")
        for view_class, method in (
            (PnlAssetView, "get"),
            (PnlChartView, "get"),
            (PnlEventsExportView, "get"),
        ):
            view = _view(view_class, CLUSTER, user=user)
            try:
                getattr(view, method)(view.request, BUNDLE, "8")
            except Http404:
                pass
            assert engine.call_args.kwargs["json"]["overrides"] == expected

    def test_pnl_views_override_payload_none(self, django_user_model):
        user = self._reader(django_user_model, SUBSCRIPTION_TIER_PERMISSIONS["Intro"])
        _override(user)
        view = _view(PnlStatusView, SUBSCRIPTION_TIER_PERMISSIONS["Intro"], user=user)
        assert view.overrides() is None
        assert "overrides" not in view.evaluate_payload()

    def test_pnl_views_override_forms_in_the_drilldown(self, django_user_model, mocker):
        user = self._reader(django_user_model)
        mocker.patch(
            "widgets.inhouse.pnl.views._engine", return_value=_deposit_events()
        )
        view = _view(PnlAssetView, ASASTATSER, user=user)
        content = view.get(view.request, BUNDLE, "8").content
        assert content.count(b">Set cost</summary>") == 1
        assert b'name="event" value="DEP/1+="' in content
        assert b">you paid" not in content
        _override(user, kind="basis", event="DEP/1+=", amount="50", currency="algo")
        content = view.get(view.request, BUNDLE, "8").content
        assert b"you paid 50 ALGO" in content
        assert b">Change cost</summary>" in content
        assert b">Remove your cost</button>" in content
        assert b'<option value="algo" selected>' in content

    def test_pnl_views_override_forms_in_the_table(self, django_user_model, mocker):
        user = self._reader(django_user_model)
        results = _grouped_results()
        results["assets"][3]["manual"] = True
        results["totals"] = {"unapplied_basis": [{}], "unapplied_values": [{}, {}]}
        _override(user, asset="7", amount="4")
        mocker.patch("widgets.inhouse.pnl.views._engine", return_value=results)
        view = _view(PnlRowsView, ASASTATSER, query="?group=unvalued", user=user)
        content = view.get(view.request).content
        assert b">Set value</summary>" in content
        assert b"Per unit" in content
        view = _view(PnlStatusView, ASASTATSER, user=user)
        mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{BUNDLE: {"-1": {"state": "finished"}}}, results],
        )
        content = view.get(view.request).content
        assert b">set by you</span>" in content
        assert b"4 USD per unit" in content
        assert b">Your value</summary>" in content
        assert b"3 of your own figures are not used" in content


WALLET = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"


@pytest.mark.django_db
class TestPnlViewsWallets:
    """Testing class for :py:class:`...pnl.views.PnlWalletsView`."""

    def _reader(self, django_user_model, permission=ASASTATSER):
        return _user(permission, django_user_model.objects.create(username="reader"))

    def _post(self, user, data, permission=ASASTATSER):
        view = _view(PnlWalletsView, permission, user=user)
        view.request = RequestFactory().post("/", data)
        view.request.user = user
        return view.post(view.request, BUNDLE)

    def test_pnl_views_wallets_add_and_remove(self, django_user_model):
        user = self._reader(django_user_model)
        for _ in range(2):
            response = self._post(user, {"address": f" {WALLET.lower()} "})
        saved = PnlOverride.objects.get(user=user)
        assert (saved.kind, saved.asset, saved.event) == ("own", "", WALLET)
        assert b'id="id-pnl-wallets"' in response.content
        assert WALLET.encode() in response.content
        assert b'role="alert"' not in response.content
        response = self._post(user, {"address": WALLET, "remove": "1"})
        assert not PnlOverride.objects.exists()
        assert b'name="remove"' not in response.content

    @pytest.mark.parametrize(
        "address,error",
        [
            ("NOTANADDRESS", b"That is not an Algorand address."),
            ("ADDRA", b"That is not an Algorand address."),
        ],
    )
    def test_pnl_views_wallets_refused(self, django_user_model, address, error):
        user = self._reader(django_user_model)
        response = self._post(user, {"address": address})
        assert error in response.content
        assert not PnlOverride.objects.exists()

    def test_pnl_views_wallets_refuses_a_bundle_address(self, django_user_model):
        user = self._reader(django_user_model)
        view = _view(PnlWalletsView, ASASTATSER, user=user)
        view.addresses = f"{WALLET} ADDRB"
        view.request = RequestFactory().post("/", {"address": WALLET})
        view.request.user = user
        response = view.post(view.request, BUNDLE)
        assert b"That address is already in this bundle." in response.content

    def test_pnl_views_wallets_limit(self, django_user_model, mocker):
        user = self._reader(django_user_model)
        mocker.patch("widgets.inhouse.pnl.views.OVERRIDES_LIMIT", 0)
        response = self._post(user, {"address": WALLET})
        assert b"At most 0 per bundle." in response.content

    def test_pnl_views_wallets_need_the_tier(self, django_user_model):
        intro = SUBSCRIPTION_TIER_PERMISSIONS["Intro"]
        user = self._reader(django_user_model, intro)
        with pytest.raises(Http404):
            self._post(user, {"address": WALLET}, permission=intro)

    def test_pnl_views_wallets_in_the_payload_and_settings(self, django_user_model):
        user = self._reader(django_user_model)
        _override(user, kind="own", asset="", event=WALLET, amount=0, currency="")
        view = _view(PnlStatusView, ASASTATSER, user=user)
        assert view.overrides() == {"own": [WALLET]}
        view = _view(PnlView, ASASTATSER, query="?tab=settings", user=user)
        view.setup(view.request)
        view.args = (BUNDLE,)
        context = view.get_context_data()
        assert [wallet.event for wallet in context["wallets"]] == [WALLET]



class TestPnlViewsLimitMessageInApp:
    """The address limit message without its subscriptions link in the app (F10)."""

    def test_pnl_views_limit_message_without_link_in_app(self, mocker):
        from core.appclient import AppClient
        from widgets.inhouse.pnl.views import ADDRESSES_LIMIT_ERROR_APP

        assert "<a" not in ADDRESSES_LIMIT_ERROR_APP
        view = _view(PnlView, ASASTATSER)
        view.request.app_client = AppClient("android", (1, 1, 0))
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            side_effect=PermissionDenied,
        )
        mocker.patch(
            "widgets.inhouse.pnl.views.addresses_limit_for_permission",
            return_value=5,
        )
        messages = mocker.patch("widgets.inhouse.pnl.views.messages")
        mocker.patch("widgets.inhouse.pnl.views.redirect", return_value="home")
        view.handle_no_permission()
        messages.error.assert_called_once_with(view.request, ADDRESSES_LIMIT_ERROR_APP % (5,))
