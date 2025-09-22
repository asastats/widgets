"""Testing module for widgets app synchronous url dispatcher module."""

from django.urls import URLResolver

from widgets import urls


class TestWidgetsUrls:
    """Testing class for :py:mod:`widgets.urls` module."""

    def _url_from_pattern(self, pattern):
        return next(url for url in urls.urlpatterns if str(url.pattern) == pattern)

    def test_widgets_urls_adds_historic_widget_url(self):
        url = self._url_from_pattern(r"^historic/")
        assert isinstance(url, URLResolver)
        assert "widgets.inhouse.historic.urls" in str(url.urlconf_name)

    def test_widgets_urls_patterns_count(self):
        assert len(urls.urlpatterns) == 1
