"""Testing module for :py:mod:`widgets.inhouse.folks.urls` module."""

from django.urls import URLPattern
from widgets.inhouse.folks import urls


class TestInhouseFolksUrls:
    """Testing class for :py:mod:`widgets.inhouse.folks.urls` module."""

    def test_inhouse_folks_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 3

    def test_inhouse_folks_urls_folks_pattern(self):
        url = urls.urlpatterns[2]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.folks.views.FolksSwapView"
        assert url.name == "folks"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"

    def test_inhouse_folks_urls_holdings_pattern(self):
        url = urls.urlpatterns[1]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.folks.views.FolksHoldingsView"
        assert url.name == "folks_holdings"
        assert str(url.pattern) == r"^(\w{58})/holdings$"

    def test_inhouse_folks_urls_assets_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.folks.views.FolksAssetsView"
        assert url.name == "folks_assets"
        assert str(url.pattern) == r"^assets$"
