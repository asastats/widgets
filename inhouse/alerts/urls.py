"""Module containing Alerts widget's URL configurations."""

from django.urls import re_path

from .views import (
    AlertsRuleDeleteView,
    AlertsRulesView,
    AlertsSubscribeView,
    AlertsUnsubscribeView,
    AlertsView,
)

#: An address or a bundle hash, as the other per-page widgets spell it.
PAGE = r"(\w{40}|\w{58})"

urlpatterns = [
    # **Before the page patterns**, and not carrying a page at all: a browser
    # subscribes once for the whole site, not per address. Putting a page in
    # the path would imply otherwise and give three ways to say the same thing.
    re_path(r"^subscribe$", AlertsSubscribeView.as_view(), name="alerts_subscribe"),
    re_path(
        r"^unsubscribe$", AlertsUnsubscribeView.as_view(), name="alerts_unsubscribe"
    ),
    # **Longest first.** The bare page pattern below would otherwise swallow
    # these, the way the Dust Sweep urls note about its own JSON endpoint.
    re_path(
        rf"^{PAGE}/rules/(?P<pk>\d+)/delete$",
        AlertsRuleDeleteView.as_view(),
        name="alerts_rule_delete",
    ),
    re_path(rf"^{PAGE}/rules$", AlertsRulesView.as_view(), name="alerts_rules"),
    re_path(rf"^{PAGE}$", AlertsView.as_view(), name="alerts"),
]
