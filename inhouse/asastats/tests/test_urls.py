"""Testing module for :py:mod:`widgets.inhouse.asastats.urls` module."""

from django.urls import URLPattern

from widgets.inhouse.asastats import urls


class TestInhouseAsastatsUrls:
    """Testing class for :py:mod:`widgets.inhouse.asastats.urls` module."""

    def test_inhouse_asastats_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 3

    def test_inhouse_asastats_urls_quote_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.asastats.views.AsastatsQuoteView"
        assert url.name == "asastats_quote"
        assert str(url.pattern) == r"^quote$"

    def test_inhouse_asastats_urls_group_pattern(self):
        url = urls.urlpatterns[1]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.asastats.views.AsastatsGroupView"
        assert url.name == "asastats_group"
        assert str(url.pattern) == r"^group$"

    def test_inhouse_asastats_urls_swap_pattern(self):
        url = urls.urlpatterns[2]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.asastats.views.AsastatsSwapView"
        assert url.name == "asastats"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"

    def test_inhouse_asastats_urls_shell_pattern_is_last(self):
        """Otherwise it swallows `quote` and `group`, which are also \\w+."""
        assert urls.urlpatterns[-1].name == "asastats"
