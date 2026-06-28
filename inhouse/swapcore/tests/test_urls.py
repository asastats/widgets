"""Testing module for :py:mod:`widgets.inhouse.swapcore.urls` module."""

from django.urls import URLPattern

from widgets.inhouse.swapcore import urls


class TestInhouseSwapcoreUrls:
    """Testing class for :py:mod:`widgets.inhouse.swapcore.urls` module."""

    def test_inhouse_swapcore_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 2

    def test_inhouse_swapcore_urls_assets_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.swapcore.views.SwapAssetsView"
        assert url.name == "swap_assets"
        assert str(url.pattern) == r"^assets$"

    def test_inhouse_swapcore_urls_holdings_pattern(self):
        url = urls.urlpatterns[1]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.swapcore.views.SwapHoldingsView"
        assert url.name == "swap_holdings"
        assert str(url.pattern) == r"^(\w{58})/holdings$"
