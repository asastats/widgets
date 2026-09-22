"""Testing module for :py:mod:`widgets.inhouse.alerts.urls` module."""

import re

import pytest

from widgets.inhouse.alerts import urls


class TestInhouseAlertsUrls:
    """Testing class for the widget's URL configuration.

    **Nothing here calls `reverse()`, and that is not an oversight.** Reversing
    forces the whole URLconf to load, which pulls in `core/views.py` and
    `utils.charts` - and `widgets/inhouse/historic/tests/conftest.py` installs a
    *fake* `utils.charts` into `sys.modules` at import time so the widget suite
    can run standalone. A `reverse()` here passes alone and fails the moment the
    suite is run whole, with an ImportError from a module this widget never
    touches. Every other widget's url test inspects the patterns instead; this
    one learned why.
    """

    def test_inhouse_alerts_urls_patterns_count(self):
        assert len(urls.urlpatterns) == 7

    def test_inhouse_alerts_urls_are_named(self):
        assert [pattern.name for pattern in urls.urlpatterns] == [
            "alerts_repriced",
            "alerts_priced",
            "alerts_subscribe",
            "alerts_unsubscribe",
            "alerts_rule_delete",
            "alerts_rules",
            "alerts",
        ]

    def test_inhouse_alerts_urls_point_at_their_views(self):
        assert [
            pattern.lookup_str.rsplit(".", 1)[-1] for pattern in urls.urlpatterns
        ] == [
            "AlertsRepricedView",
            "AlertsPricedView",
            "AlertsSubscribeView",
            "AlertsUnsubscribeView",
            "AlertsRuleDeleteView",
            "AlertsRulesView",
            "AlertsView",
        ]

    def test_inhouse_alerts_urls_put_the_longest_first(self):
        """**Order decides correctness here.** The bare page pattern would
        swallow `<page>/rules` and `<page>/rules/<pk>/delete` if it came first,
        the way the Dust Sweep urls note about its own JSON endpoint."""
        names = [pattern.name for pattern in urls.urlpatterns]

        assert names.index("alerts_rule_delete") < names.index("alerts_rules")
        assert names.index("alerts_rules") < names.index("alerts")

    def test_inhouse_alerts_urls_match_an_address_and_a_bundle(self):
        pattern = re.compile(
            str(next(p for p in urls.urlpatterns if p.name == "alerts").pattern)
        )

        assert pattern.match("A" * 58)  # an address
        assert pattern.match("A" * 40)  # a bundle hash
        assert not pattern.match("A" * 39)

    def test_inhouse_alerts_urls_repriced_carries_no_page(self):
        """**The page it acts on is in the signed body, not the path.** A page
        in the URL would be the one part of the request the signature did not
        cover, which is the whole point of signing the body."""
        pattern = str(
            next(
                p for p in urls.urlpatterns if p.name == "alerts_repriced"
            ).pattern
        )

        assert "58" not in pattern and "40" not in pattern

    def test_inhouse_alerts_urls_priced_carries_no_page(self):
        """A price rule belongs to an asset rather than to a page, and the
        assets are in the signed body."""
        pattern = str(
            next(p for p in urls.urlpatterns if p.name == "alerts_priced").pattern
        )

        assert "58" not in pattern and "40" not in pattern

    def test_inhouse_alerts_urls_priced_is_not_swallowed_by_repriced(self):
        """**`^priced$` and `^repriced$`, both anchored.** Without the anchors
        the shorter pattern matches inside the longer one, and every trigger
        from the live pass would be evaluated as a price body - answering 400
        for a call that was perfectly well formed."""
        priced = re.compile(
            str(next(p for p in urls.urlpatterns if p.name == "alerts_priced").pattern)
        )

        assert priced.match("priced")
        assert not priced.match("repriced")

    def test_inhouse_alerts_urls_subscribe_carries_no_page(self):
        """A browser subscribes once for the whole site, not per address. A page
        in the path would imply otherwise and give three ways to say one thing.
        """
        pattern = str(
            next(
                p for p in urls.urlpatterns if p.name == "alerts_subscribe"
            ).pattern
        )

        assert "58" not in pattern and "40" not in pattern


@pytest.mark.django_db
class TestInhouseAlertsUrlsDelivery:
    """Testing class for *how* a matched route hands the page to its view.

    **The gap that let a 500 ship.** Every other test in this widget calls a
    view directly with `bundle` already set, so none of them ran `test_func`
    against what Django would really pass - and `test_func` read `self.args[0]`.
    Django sends every captured group as a *keyword* when any one of them is
    named, so the delete route, which names `pk`, left `args` empty and raised
    `IndexError`. Removing a rule answered 500 from the day it was written.
    """

    def _match(self, name, path):
        """Return what Django would hand a view for `path` on route `name`."""
        pattern = next(p for p in urls.urlpatterns if p.name == name)
        return pattern.resolve(path)

    @pytest.mark.parametrize(
        ("name", "path"),
        [
            ("alerts", "A" * 58),
            ("alerts_rules", "A" * 58 + "/rules"),
            ("alerts_rule_delete", "A" * 58 + "/rules/7/delete"),
        ],
    )
    def test_inhouse_alerts_urls_every_route_delivers_the_page_as_a_keyword(
        self, name, path
    ):
        """**All three the same way**, which is the whole point of naming the
        group: a view can read `kwargs["page"]` without knowing which route it
        was reached by."""
        match = self._match(name, path)

        assert match is not None, name
        assert match.kwargs.get("page") == "A" * 58
        assert match.args == (), "a named group anywhere sends them all to kwargs"

    def test_inhouse_alerts_urls_delete_still_carries_its_pk(self):
        match = self._match("alerts_rule_delete", "A" * 58 + "/rules/7/delete")

        assert match.kwargs["pk"] == "7"
