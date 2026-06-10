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


class BaseUserCreatedView(BaseView):
    def setup_method(self):
        # # Setup user
        username = "user{}".format(str(time.time())[5:])
        self.user = get_user_model().objects.create(
            email="{}@testuser.com".format(username),
            username=username,
        )
        self.user.set_password("12345o")
        self.user.save()
        # self.set_permission()

        # Setup request
        self.request = RequestFactory().get("/fake-path")
        self.request.user = self.user

    # def set_permission(self, permission=258_885_438_201):
    #     self.user.profile.permission = permission
    #     self.user.profile.save()


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


class TestBaseUserPassesTestMixinDb(BaseUserCreatedView):
    """Testing class for :class:`widgets.views.BaseUserPassesTestMixin` for database."""

    # # test_func
    @pytest.mark.django_db
    def test_widgets_baseuserpassestestmixin_test_func_functionality(self, mocker):
        # Setup view
        view = BaseUserPassesTestMixin()
        view = self.setup_view(view, self.request)
        callback = mocker.MagicMock()
        callback.return_value = True
        self.user.profile = mocker.MagicMock()
        arg1, arg2 = 1, 2
        # Run.
        test_func = view.test_func(callback, arg1, arg2)
        # Check.
        assert test_func is True
        callback.assert_called_once_with(self.request.user.profile, arg1, arg2)
