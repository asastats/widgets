"""Testing module for :py:mod:`widgets.inhouse.pnl.views` module."""

import types

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.pnl.models import PnlBundle
from widgets.inhouse.pnl.views import (
    PnlAssetView,
    PnlProcessView,
    PnlRemoveView,
    PnlStatusView,
    PnlView,
    addresses_in_use,
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
        mocker.patch(
            "widgets.inhouse.pnl.views.is_linked_to_user", side_effect=linked
        )
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
        [(0, 1, "subscriptions"), (ASASTATSER, 1, "home"), (ASASTATSER, 0, "subscriptions")],
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
        assert b"hx-trigger=\"load delay:3s\"" in response.content

    def test_pnl_views_status_offers_processing(self, mocker):
        engine = mocker.patch(
            "widgets.inhouse.pnl.views._engine",
            side_effect=[{}, {"type": "show_update"}],
        )
        view = _view(PnlStatusView)
        response = view.get(view.request)
        assert b"Process" in response.content
        assert engine.call_args.kwargs == {"json": {"currency": "usd"}}

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
        assert b"hx-get=\"/widgets/pnl/" in response.content


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
        view = _view(PnlProcessView, SUBSCRIPTION_TIER_PERMISSIONS["Professional"], user=user)
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
                }
            ],
        }
        engine = mocker.patch("widgets.inhouse.pnl.views._engine", return_value=data)
        view = _view(PnlAssetView, ASASTATSER, "?currency=algo")
        response = view.get(view.request, BUNDLE, "5")
        assert b"Income" in response.content
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
        ],
    )
    def test_pnl_urls_resolve(self, suffix, view_class):
        assert resolve(f"/widgets/pnl/{BUNDLE}{suffix}").func.view_class is view_class
