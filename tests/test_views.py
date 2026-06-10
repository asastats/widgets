"""Testing module for :py:mod:`asastats.widgets.views` module."""

import time
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from widgets.views import BaseUserPassesTestMixin


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
        self.user = AnonymousUser()
        # Setup request
        self.request = RequestFactory().get("/fake-path")
        self.request.user = self.user


class TestBaseUserPassesTestMixin(BaseView):
    """Testing class for :class:`widgets.views.BaseUserPassesTestMixin`."""

    def test_widgets_baseuserpassestestmixin_is_subclass_of_userpassestestmixin(self):
        assert issubclass(BaseUserPassesTestMixin, UserPassesTestMixin)

    # # test_func
    def test_widgets_baseuserpassestestmixin_test_func_for_anonymouns_user(
        self, mocker
    ):
        # Setup view
        view = BaseUserPassesTestMixin()
        view = self.setup_view(view, self.request)
        callback = mocker.MagicMock()
        arg1, arg2 = 1, 2
        # Run.
        test_func = view.test_func(callback, arg1, arg2)
        # Check.
        assert test_func is False
        callback.assert_not_called()

    def test_widgets_baseuserpassestestmixin_test_func_functionality(self, mocker):
        # Setup view
        view = BaseUserPassesTestMixin()
        view = self.setup_view(view, self.request)
        callback = mocker.MagicMock()
        callback.return_value = True
        mock_user = mocker.MagicMock()
        self.request.user = mock_user
        arg1, arg2 = 1, 2
        # Run.
        test_func = view.test_func(callback, arg1, arg2)
        # Check.
        assert test_func is True
        # Assert against the mock_user's profile attribute
        callback.assert_called_once_with(mock_user.profile, arg1, arg2)
