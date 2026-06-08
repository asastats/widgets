"""Module containing historic widget's views."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.views.generic.base import RedirectView, TemplateView

from api.client import engine_request
from api.widgets import bundle_and_addresses_from_path

from widgethost.enforcement import WidgetAccessMixin
from widgethost.manifest import addresses_limit_for_permission

from .manifest import MANIFEST

ADDRESSES_LIMIT_ERROR = (
    "Your <a href='/subscriptions/' target='_blank' rel='noopener'>subscription tier"
    "</a> allows you to evaluate historic data for up to %s address(es)."
)


class HistoricView(WidgetAccessMixin, TemplateView):
    """View for presenting historic account data.

    :var template_name: relative path to Django template's name for view
    :type template_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    :var bundle: hash made from public Algorand address(es)
    :type bundle: str
    :var addresses: space separated collection of public Algorand addresses
    :type addresses: str
    """

    template_name = "historic/index.html"
    manifest = MANIFEST
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
        """Calls super method and redirect to subscribe page on exception.

        :var limit: number of addresses the user's permission allows
        :type limit: int
        """
        try:
            return super().handle_no_permission()

        except PermissionDenied:
            limit = addresses_limit_for_permission(
                self.manifest.required_permission,
                self.request.user.profile.permission,
            )
            if limit:
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
        return self.manifest_test_func(len(self.addresses.split(" ")))


class HistoricResetView(WidgetAccessMixin, RedirectView):
    """View for deleting existing bundle data.

    :var permanent: is redirection permanent or not
    :type permanent: Boolean
    :var pattern_name: name of the url to redirect to
    :type pattern_name: str
    :var manifest: this widget's parsed manifest
    :type manifest: :class:`widgethost.manifest.Manifest`
    """

    permanent = False
    pattern_name = "historic"
    manifest = MANIFEST

    def get(self, request, *args, **kwargs):
        """Delete the bundle's engine data after the gate, then redirect.

        The permission gate runs in ``dispatch`` before this method, so the
        destructive reset only fires for an authorized request.

        :param request: Django request object
        :type request: :class:`django.http.HttpRequest`
        :var bundle: bundle hash to delete data for
        :type bundle: str
        """
        bundle = args[0]
        engine_request(
            "historic:reset",
            "DELETE",
            f"/api/v2/historic/{bundle}/",
            self.manifest.engine_endpoints,
        )
        return super().get(request, *args, **kwargs)

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
        return self.manifest_test_func(len(self.addresses.split(" ")))
