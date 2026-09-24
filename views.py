"""Module containing widgets app views' base classes."""

from django.contrib.auth.mixins import UserPassesTestMixin


class BaseUserPassesTestMixin(UserPassesTestMixin):
    """Gate a widget view on a check against the requesting profile."""

    def test_func(self, callback, *args):
        """Check whether the requesting user's profile passes `callback`.

        :param callback: callable taking the profile and `args`
        :type callback: object
        :param args: positional arguments for the callback
        :type args: list
        :return: Boolean
        """
        return (
            self.request.user.is_authenticated
            and self.request.user.profile
            and callback(self.request.user.profile, *args)
        )
