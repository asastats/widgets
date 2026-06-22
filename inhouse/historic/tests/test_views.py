"""Testing module for :py:mod:`widgets.inhouse.historic.views` module."""

from django.core.exceptions import PermissionDenied
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
        gate = mocker.patch.object(
            HistoricView, "manifest_test_func", return_value=True
        )
        assert view.test_func() is True
        assert view.bundle == "BUNDLE"
        assert view.addresses == "A1 A2"
        resolver.assert_called_once_with("ABCD", force_bundle=True)
        gate.assert_called_once_with(2)

    def test_historic_views_historic_view_get_context_data(self, mocker):
        view = HistoricView()
        view.bundle = "BUNDLE"
        view.addresses = "A1 A2"
        mocker.patch(
            "django.views.generic.base.ContextMixin.get_context_data",
            return_value={},
        )
        context = view.get_context_data()
        assert context["bundle"] == "BUNDLE"
        assert context["addresses"] == "A1 A2"

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
            "widgets.inhouse.historic.views.redirect", return_value="subscriptions"
        )
        assert view.handle_no_permission() == "subscriptions"
        redirect.assert_called_once_with("subscriptions")

    def test_historic_views_historic_view_handle_no_permission_passthrough(
        self, mocker
    ):
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
