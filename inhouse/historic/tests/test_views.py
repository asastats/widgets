"""Testing module for :py:mod:`widgets.inhouse.historic.views` module."""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.template.loader import get_template

from widgets.inhouse.historic.views import HistoricResetView, HistoricView


class TestHistoricViewsHistoricView:
    """Testing class for :py:class:`...historic.views.HistoricView`."""

    def test_historic_views_historic_view_test_func(self, mocker):
        view = HistoricView()
        view.args = ("abcd",)
        resolver = mocker.patch(
            "widgets.inhouse.historic.views.bundle_and_addresses_from_path",
            return_value=("BUNDLE", "A1 A2"),
        )
        gate = mocker.patch.object(HistoricView, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        assert view.bundle == "BUNDLE"
        assert view.addresses == "A1 A2"
        resolver.assert_called_once_with("ABCD", force_bundle=True)
        gate.assert_called_once_with(2)

    def test_historic_views_historic_view_get_context_data(self, mocker):
        view = HistoricView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLE"
        view.addresses = "A1 A2"
        mocker.patch(
            "django.views.generic.base.ContextMixin.get_context_data",
            return_value={},
        )
        fiat = mocker.patch(
            "widgets.inhouse.historic.views.fiat_for_user",
            return_value={"code": "EUR", "rate": 0.9, "symbol": "€"},
        )
        context = view.get_context_data()
        assert context["bundle"] == "BUNDLE"
        assert context["addresses"] == "A1 A2"
        assert context["website_name"] == settings.WEBSITE_NAME
        assert context["fiat"]["code"] == "EUR"
        fiat.assert_called_once_with(view.request.user)

    def test_historic_views_historic_view_handle_no_permission_address_limit(
        self, mocker
    ):
        view = HistoricView()
        view.manifest = mocker.MagicMock()
        view.request = mocker.MagicMock()
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            side_effect=PermissionDenied,
        )
        mocker.patch(
            "widgets.inhouse.historic.views.addresses_limit_for_permission",
            return_value=5,
        )
        messages = mocker.patch("widgets.inhouse.historic.views.messages")
        redirect = mocker.patch(
            "widgets.inhouse.historic.views.redirect", return_value="home"
        )
        assert view.handle_no_permission() == "home"
        redirect.assert_called_once_with("home")
        assert messages.error.called

    def test_historic_views_historic_view_handle_no_permission_subscribe(self, mocker):
        view = HistoricView()
        view.manifest = mocker.MagicMock()
        view.request = mocker.MagicMock()
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            side_effect=PermissionDenied,
        )
        mocker.patch(
            "widgets.inhouse.historic.views.addresses_limit_for_permission",
            return_value=0,
        )
        redirect = mocker.patch(
            "widgets.inhouse.historic.views.subscriptions_redirect",
            return_value="subscriptions",
        )
        assert view.handle_no_permission() == "subscriptions"
        redirect.assert_called_once_with(view.request)

    def test_historic_views_historic_view_handle_no_permission_passthrough(self, mocker):
        view = HistoricView()
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            return_value="login",
        )
        assert view.handle_no_permission() == "login"


class TestHistoricViewsHistoricResetView:
    """Testing class for :py:class:`...historic.views.HistoricResetView`."""

    def test_historic_views_historic_reset_view_get(self, mocker):
        view = HistoricResetView()
        view.manifest = mocker.MagicMock(engine_endpoints=["historic:reset"])
        engine = mocker.patch("widgets.inhouse.historic.views.engine_request")
        parent = mocker.patch(
            "django.views.generic.base.RedirectView.get", return_value="redirect"
        )
        assert view.get(mocker.MagicMock(), "BUNDLE") == "redirect"
        engine.assert_called_once_with(
            "historic:reset",
            "DELETE",
            "/api/v2/historic/BUNDLE/",
            ["historic:reset"],
        )
        assert parent.called

    def test_historic_views_historic_reset_view_test_func(self, mocker):
        view = HistoricResetView()
        view.args = ("abcd",)
        mocker.patch(
            "widgets.inhouse.historic.views.bundle_and_addresses_from_path",
            return_value=("BUNDLE", "A1"),
        )
        gate = mocker.patch.object(
            HistoricResetView, "manifest_test_func", return_value=True
        )
        assert view.test_func() is True
        gate.assert_called_once_with(1)

    def test_historic_views_historic_reset_view_get_redirect_url(self, mocker):
        view = HistoricResetView()
        parent = mocker.patch(
            "django.views.generic.base.RedirectView.get_redirect_url",
            return_value="/url/",
        )
        assert view.get_redirect_url("BUNDLE") == "/url/"
        parent.assert_called_once_with("BUNDLE")


class TestHistoricViewsIndexTemplate:
    """Testing class for the ``historic/index.html`` template."""

    def test_historic_views_index_keeps_the_socket_open_in_the_background(self):
        source = get_template("historic/index.html").template.source
        assert """hx-config='{"ws": {"pauseOnBackground": false}}'""" in source



class TestHistoricViewsTitle:
    """The page names the address, not its internal hash, for one address."""

    def _title(self, addresses):
        import re

        from django.template import Context, Template

        source = get_template("historic/index.html").template.source
        h4 = re.search(r"\{% with addrs=.*?\{% endwith %\}", source).group(0)
        return Template("{% load core_extras %}" + h4).render(
            Context({"bundle": "C38DC" + "0" * 30 + "10748", "addresses": addresses})
        )

    def test_historic_views_title_single_address(self):
        html = self._title("ZRNRW" + "A" * 48 + "LMQPM")
        assert ">ZRNRW...LMQPM</h4>" in html
        assert 'title="C38DC' in html

    def test_historic_views_title_bundle_keeps_its_hash(self):
        html = self._title("A" * 58 + " " + "B" * 58)
        assert ">C38DC...10748</h4>" in html

    def test_historic_views_processing_single_address_total_row(self):
        from django.template.loader import render_to_string

        address = "ZRNRW" + "A" * 48 + "LMQPM"
        html = render_to_string(
            "historic/processing.html",
            {"bundle": "C38DC", "addresses": [address, "C38DC" + "0" * 35]},
        )
        assert "<h5>ZRNRW...LMQPM total</h5>" in html
        assert "C38DC...00000" not in html


class TestHistoricViewsLimitMessageInApp:
    """The address limit message without its subscriptions link in the app (F10)."""

    def test_historic_views_limit_message_without_link_in_app(self, mocker):
        from core.appclient import AppClient
        from widgets.inhouse.historic.views import ADDRESSES_LIMIT_ERROR_APP

        assert "<a" not in ADDRESSES_LIMIT_ERROR_APP
        view = HistoricView()
        view.manifest = mocker.MagicMock()
        view.request = mocker.MagicMock()
        view.request.app_client = AppClient("android", (1, 1, 0))
        mocker.patch(
            "django.contrib.auth.mixins.AccessMixin.handle_no_permission",
            side_effect=PermissionDenied,
        )
        mocker.patch(
            "widgets.inhouse.historic.views.addresses_limit_for_permission",
            return_value=5,
        )
        messages = mocker.patch("widgets.inhouse.historic.views.messages")
        mocker.patch("widgets.inhouse.historic.views.redirect", return_value="home")
        view.handle_no_permission()
        messages.error.assert_called_once_with(view.request, ADDRESSES_LIMIT_ERROR_APP % (5,))
