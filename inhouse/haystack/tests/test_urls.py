"""Testing module for :py:mod:`widgets.inhouse.haystack.urls` module."""

from django.urls import URLPattern
from widgets.inhouse.haystack import urls


class TestInhouseHaystackUrls:
    """Testing class for :py:mod:`widgets.inhouse.haystack.urls` module."""

    def test_inhouse_haystack_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 3

    def test_inhouse_haystack_urls_haystack_pattern(self):
        url = urls.urlpatterns[2]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.haystack.views.HaystackSwapView"
        assert url.name == "haystack"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"

    def test_inhouse_haystack_urls_holdings_pattern(self):
        url = urls.urlpatterns[1]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.haystack.views.HaystackHoldingsView"
        assert url.name == "haystack_holdings"
        assert str(url.pattern) == r"^(\w{58})/holdings$"

    def test_inhouse_haystack_urls_assets_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.haystack.views.HaystackAssetsView"
        assert url.name == "haystack_assets"
        assert str(url.pattern) == r"^assets$"
