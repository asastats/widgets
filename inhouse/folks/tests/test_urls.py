"""Testing module for :py:mod:`widgets.inhouse.folks.urls` module."""

from django.urls import URLPattern

from widgets.inhouse.folks import urls


class TestInhouseFolksUrls:
    """Testing class for :py:mod:`widgets.inhouse.folks.urls` module."""

    def test_inhouse_folks_urls_single_pattern(self):
        assert len(urls.urlpatterns) == 1

    def test_inhouse_folks_urls_folks_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.folks.views.FolksSwapView"
        assert url.name == "folks"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"
