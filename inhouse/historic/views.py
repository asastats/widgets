"""Module containing historic widget's views."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.views.generic.base import RedirectView, TemplateView

from api.widgets import bundle_and_addresses_from_path
from storage.main import reset_bundle_historic_data
from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.views import BaseUserPassesTestMixin

from .permissions import TIERS_ADDRESSES_LIMIT, ADDRESSES_LIMIT_ERROR, can_access


class HistoricView(BaseUserPassesTestMixin, TemplateView):
    """View for presenting historic account data.

    :var template_name: relative path to Django template's name for view
    :type template_name: str
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "historic/index.html"
    bundle = None
    addresses = None

    def get_context_data(self, *args, **kwargs):
        """Update context with bundle and addresses retrieved from URL.

        TODO: named bundle URL should be added too

        :var context: object containing all the data needed for template rendering
        :type context: dict
        :return: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context["bundle"] = self.bundle
        context["addresses"] = self.addresses
        return context

    def handle_no_permission(self):
        """Calls super method and redirect to subscribe page on exception."""
        try:
            return super().handle_no_permission()

        except PermissionDenied:
            if (
                self.request.user.profile.permission
                >= SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]
            ):
                limit = TIERS_ADDRESSES_LIMIT.get(self.request.user.profile.tier_name())
                messages.error(
                    self.request, mark_safe(ADDRESSES_LIMIT_ERROR % (limit,))
                )
                return redirect("home")

            return redirect("subscriptions")

    def test_func(self):
        """Return True if user has enough permission to access historic data widget.

        :var url_path: address or bundle value found in URL
        :type url_path: str
        :return: Boolean
        """
        url_path = self.args[0].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return super().test_func(can_access, len(self.addresses.split(" ")))


class HistoricResetView(BaseUserPassesTestMixin, RedirectView):
    """View for deleting existing bundle data.

    :var permanent: is redirection permanent or not
    :type permanent: Boolean
    :var pattern_name: name of the url to redirect to
    :type pattern_name: str
    """

    permanent = False
    pattern_name = "historic"

    def dispatch(self, request, *args, **kwargs):
        """Central method responsible for deleting data and redirect.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var bundle: bundle hash to delete data for
        :type bundle: str
        """
        bundle = args[0]
        reset_bundle_historic_data(bundle)
        return super().dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        """Return URL for bundle historic page."""
        return super().get_redirect_url(args[0], **kwargs)

    def test_func(self):
        """Return True if user has enough permission to access historic data widget.

        :var url_path: address or bundle value found in URL
        :type url_path: str
        :return: Boolean
        """
        url_path = self.args[0].upper()
        self.bundle, self.addresses = bundle_and_addresses_from_path(
            url_path, force_bundle=True
        )
        return super().test_func(can_access, len(self.addresses.split(" ")))
