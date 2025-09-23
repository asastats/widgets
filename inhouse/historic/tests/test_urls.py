"""Testing module for historic widget synchronous url dispatcher module."""

from django.urls import URLPattern

from inhouse.historic import urls


class TestWidgetsHistoricUrls:
    """Testing class for :py:mod:`inhouse.historic.urls` module."""

    def _url_from_pattern(self, pattern):
        return next(url for url in urls.urlpatterns if str(url.pattern) == pattern)

    def test_widgets_inhouse_historic_urls_historic(self):
        url = self._url_from_pattern(r"^(\w{40}|\w{58})$")
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "inhouse.historic.views.HistoricView"
        assert url.name == "historic"

    def test_widgets_inhouse_historic_urls_historic_reset(self):
        url = self._url_from_pattern(r"^(\w{40})/reset$")
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "inhouse.historic.views.HistoricResetView"
        assert url.name == "historic_reset"

    def test_widgets_inhouse_historic_urls_patterns_count(self):
        assert len(urls.urlpatterns) == 2
