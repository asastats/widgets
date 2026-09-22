"""Module containing Alerts widget's URL configurations."""

from django.urls import re_path

from .views import (
    AlertsPricedView,
    AlertsRepricedView,
    AlertsRuleDeleteView,
    AlertsRuleEditView,
    AlertsRulesView,
    AlertsSubscribeView,
    AlertsUnsubscribeView,
    AlertsView,
)

#: An address or a bundle hash, as the other per-page widgets spell it.
#:
#: **Named, and it has to be.** Django hands a view *either* positional groups
#: or keyword ones, never both: one named group anywhere in a pattern sends all
#: of them to `kwargs` and leaves `args` empty. The delete route has a named
#: `pk`, so a view reading `self.args[0]` raised `IndexError` there and answered
#: 500 - while the two routes without a `pk` worked. Naming this one makes every
#: route deliver the page the same way.
PAGE = r"(?P<page>\w{40}|\w{58})"

urlpatterns = [
    # The engine's trigger, and the only pattern here no reader ever reaches.
    # It carries no page for the same reason subscribe carries none: it names
    # its page in the body, which is the half it signs.
    re_path(r"^repriced$", AlertsRepricedView.as_view(), name="alerts_repriced"),
    # The other machine caller: the periodic price task, which carries prices
    # rather than naming a page. Two endpoints rather than one body that means
    # two things, so neither has to ask what shape it was given.
    re_path(r"^priced$", AlertsPricedView.as_view(), name="alerts_priced"),
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
    re_path(
        rf"^{PAGE}/rules/(?P<pk>\d+)/edit$",
        AlertsRuleEditView.as_view(),
        name="alerts_rule_edit",
    ),
    re_path(rf"^{PAGE}/rules$", AlertsRulesView.as_view(), name="alerts_rules"),
    re_path(rf"^{PAGE}$", AlertsView.as_view(), name="alerts"),
]
