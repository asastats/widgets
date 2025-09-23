"""Testing module for historic widget views module."""

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.views.generic.base import RedirectView, TemplateView

from inhouse.historic.permissions import (
    ADDRESSES_LIMIT_ERROR,
    SUBSCRIPTION_TIER_PERMISSIONS,
    can_access,
)
from inhouse.historic.views import HistoricResetView, HistoricView
from views import BaseUserPassesTestMixin


class BaseView:
    """Base helper class for testing views."""

    def setup_view(self, view, request, *args, **kwargs):
        """Mimic as_view() returned callable, but returns view instance.

        args and kwargs are the same as those passed to ``reverse()``

        """
        view.request = request
        view.args = args
        view.kwargs = kwargs
        return view

    # # helper methods
    def setup_method(self):
        # Setup request
        self.request = RequestFactory().get("/fake-path")


class TestWidgetsHistoricView(BaseView):
    """Testing class for :class:`inhouse.historic.HistoricView`."""

    def test_widgets_historicview_is_subclass_of_baseuserpassestestmixin(self):
        assert issubclass(HistoricView, BaseUserPassesTestMixin)

    def test_widgets_historicview_is_subclass_of_templateview(self):
        assert issubclass(HistoricView, TemplateView)

    # # get_context_data
    def test_widgets_historicview_get_context_data_functionality(self, mocker):
        # Setup view
        view = HistoricView()
        url_path = "url_path"
        view = self.setup_view(view, self.request, url_path)
        bundle, addresses = "bundle", "addresses"
        mocker.patch(
            "inhouse.historic.views.bundle_and_addresses_from_path",
            return_value=(bundle, addresses),
        )
        mocker.patch("inhouse.historic.views.BaseUserPassesTestMixin.test_func")
        # Run.
        view.test_func()
        context = view.get_context_data()
        # Check.
        assert context == {"view": view, "bundle": bundle, "addresses": addresses}

    # # handle_no_permission
    def test_widgets_historicview_handle_no_permission_calls_and_returns_super(
        self, mocker
    ):
        view = HistoricView()
        self.request.user = mocker.MagicMock()
        self.request.user.profile.permission = SUBSCRIPTION_TIER_PERMISSIONS["Intro"]
        view = self.setup_view(view, self.request)
        with mock.patch(
            "inhouse.historic.views.BaseUserPassesTestMixin.handle_no_permission"
        ) as mocked_super:
            returned = view.handle_no_permission()
            assert returned == mocked_super.return_value
            mocked_super.assert_called_once_with()

    def test_widgets_historicview_handle_no_permission_redirects_on_exception(
        self, mocker
    ):
        mocked_redirect = mocker.patch("inhouse.historic.views.redirect")
        view = HistoricView()
        self.request.user = mocker.MagicMock()
        self.request.user.profile.permission = (
            SUBSCRIPTION_TIER_PERMISSIONS["Intro"] - 1
        )
        view = self.setup_view(view, self.request)
        with mock.patch(
            "inhouse.historic.views.BaseUserPassesTestMixin.handle_no_permission"
        ) as mocked_super, mock.patch(
            "inhouse.historic.views.messages"
        ) as mocked_messages, mock.patch(
            "inhouse.historic.views.mark_safe"
        ) as mocked_safe:
            mocked_super.side_effect = PermissionDenied("", "", 0)
            returned = view.handle_no_permission()
            mocked_safe.assert_not_called()
            mocked_messages.error.assert_not_called()
        assert returned == mocked_redirect.return_value
        mocked_redirect.assert_called_once_with("subscriptions")

    def test_widgets_historicview_handle_no_permission_redirects_for_asastatser_limit(
        self, mocker
    ):
        mocked_redirect = mocker.patch("inhouse.historic.views.redirect")
        view = HistoricView()
        self.request.user = mocker.MagicMock()
        self.request.user.profile.tier_name.return_value = "Asastatser"
        self.request.user.profile.permission = SUBSCRIPTION_TIER_PERMISSIONS[
            "Asastatser"
        ]
        view = self.setup_view(view, self.request)
        with mock.patch(
            "inhouse.historic.views.BaseUserPassesTestMixin.handle_no_permission"
        ) as mocked_super, mock.patch(
            "inhouse.historic.views.messages"
        ) as mocked_messages, mock.patch(
            "inhouse.historic.views.mark_safe"
        ) as mocked_safe:
            mocked_super.side_effect = PermissionDenied("", "", 0)
            returned = view.handle_no_permission()
            mocked_safe.assert_called_once_with(ADDRESSES_LIMIT_ERROR % (1,))
            mocked_messages.error.assert_called_once_with(
                self.request, mocked_safe.return_value
            )
        assert returned == mocked_redirect.return_value
        mocked_redirect.assert_called_once_with("home")

    # # test_func
    def test_widgets_historicview_test_func_functionality(self, mocker):
        # Setup view
        view = HistoricView()
        view = self.setup_view(view, self.request)
        view.args = ["url-path"]
        bundle, addresses = "bundle", "address1 address2"
        mocked_bundle = mocker.patch(
            "inhouse.historic.views.bundle_and_addresses_from_path",
            return_value=(bundle, addresses),
        )
        mocked_test_func = mocker.patch(
            "inhouse.historic.views.BaseUserPassesTestMixin.test_func"
        )
        # Run.
        test_func = view.test_func()
        # Check.
        assert test_func == mocked_test_func.return_value
        mocked_bundle.assert_called_once_with("URL-PATH", force_bundle=True)
        mocked_test_func.assert_called_once_with(can_access, len(addresses.split(" ")))


class TestWidgetsHistoricResetView(BaseView):
    """Testing class for :class:`inhouse.historic.HistoricResetView`."""

    def test_widgets_historicresetview_is_subclass_of_baseuserpassestestmixin(self):
        assert issubclass(HistoricResetView, BaseUserPassesTestMixin)

    def test_widgets_historicresetview_is_subclass_of_redirectview(self):
        assert issubclass(HistoricResetView, RedirectView)

    # # dispatch
    def test_widgets_historicresetview_dispatch_functionality(self, mocker):
        # Setup view
        view = HistoricResetView()
        view = self.setup_view(view, self.request)
        view.args = ["bundle"]
        mocked_reset = mocker.patch("inhouse.historic.views.reset_bundle_historic_data")
        mocked_dispatch = mocker.patch("inhouse.historic.views.RedirectView.dispatch")
        mocker.patch(
            "inhouse.historic.views.HistoricResetView.test_func",
        )
        # Run.
        dispatch = view.dispatch(self.request, "bundle")
        # Check.
        assert dispatch == mocked_dispatch.return_value
        mocked_reset.assert_called_once_with("bundle")
        mocked_dispatch.assert_called_once_with(self.request, "bundle")

    # # get_redirect_url
    def test_widgets_historicresetview_get_redirect_url_functionality(self, mocker):
        # Setup view
        view = HistoricResetView()
        view = self.setup_view(view, self.request)
        view.args = ["bundle"]
        mocked_url = mocker.patch(
            "inhouse.historic.views.RedirectView.get_redirect_url"
        )
        # Run.
        url = view.get_redirect_url("bundle")
        # Check.
        assert url == mocked_url.return_value
        mocked_url.assert_called_once_with("bundle")

    # # test_func
    def test_widgets_historicresetview_test_func_functionality(self, mocker):
        # Setup view
        view = HistoricResetView()
        view = self.setup_view(view, self.request)
        view.args = ["url-path"]
        bundle, addresses = "bundle", "addresses"
        mocked_bundle = mocker.patch(
            "inhouse.historic.views.bundle_and_addresses_from_path",
            return_value=(bundle, addresses),
        )
        mocked_test_func = mocker.patch(
            "inhouse.historic.views.BaseUserPassesTestMixin.test_func"
        )
        # Run.
        test_func = view.test_func()
        # Check.
        assert test_func == mocked_test_func.return_value
        mocked_bundle.assert_called_once_with("URL-PATH", force_bundle=True)
        mocked_test_func.assert_called_once_with(can_access, len(addresses.split(" ")))
