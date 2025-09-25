"""Module containing widgets app views' base classes."""

from django.contrib.auth.mixins import UserPassesTestMixin


class BaseUserPassesTestMixin(UserPassesTestMixin):
    """View for presenting historic account data."""

    # def dispatch(self, request, *args, **kwargs):
    #     """Retrieve address(es) from URL value which will be evaluated.

    #     :param request: Django request object
    #     :type request: :class:`django.http.HttpRequest`
    #     :var url_value: address or bundle value found in url
    #     :type url_value: str
    #     :var addresses: public Algorand addresses separated by spaces
    #     :type addresses: str
    #     :return: object
    #     """
    #     url_value = self.args[0].upper()
    #     check_forbidden_addresses(url_value)

    #     if len(url_value) < 51:
    #         addresses = check_bundle_addresses(url_value)
    #         if addresses == "":
    #             return redirect("index")
    #         check_forbidden_addresses(addresses)

    #     return super().dispatch(request, *args, **kwargs)

    def test_func(self, callback, *args):
        """Check if user has enough permission to access historic data widget.

        :param callback: callback function accepting profile and provided argument
        :type callback: object
        :param args: collection of positional arguments for the callback funtion
        :type args: list
        :return: Boolean
        """
        return (
            self.request.user.is_authenticated
            and self.request.user.profile
            and callback(self.request.user.profile, *args)
        )
