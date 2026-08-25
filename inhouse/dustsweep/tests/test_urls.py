"""Testing module for :py:mod:`widgets.inhouse.dustsweep.urls` module."""

from django.urls import URLPattern

from widgets.inhouse.dustsweep import urls


class TestInhouseDustsweepUrls:
    """Testing class for :py:mod:`widgets.inhouse.dustsweep.urls` module."""

    def test_inhouse_dustsweep_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 2

    def test_inhouse_dustsweep_urls_plan_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.dustsweep.views.DustSweepPlanView"
        assert url.name == "dustsweep_plan"
        assert str(url.pattern) == r"^plan$"

    def test_inhouse_dustsweep_urls_shell_pattern(self):
        url = urls.urlpatterns[1]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.dustsweep.views.DustSweepView"
        assert url.name == "dustsweep"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"

    def test_inhouse_dustsweep_urls_shell_pattern_is_last(self):
        """Otherwise it swallows `plan`, which is also \\w+.

        A 40-or-58 character class does not match "plan", but the shell pattern
        is the one that would grow - and the asastats widget has the same
        ordering for the same reason.
        """
        assert urls.urlpatterns[-1].name == "dustsweep"
