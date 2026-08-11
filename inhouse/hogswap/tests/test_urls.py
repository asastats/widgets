"""Testing module for :py:mod:`widgets.inhouse.hogswap.urls` module."""

from django.urls import URLPattern

from widgets.inhouse.hogswap import urls


class TestInhouseHogswapUrls:
    """Testing class for :py:mod:`widgets.inhouse.hogswap.urls` module."""

    def test_inhouse_hogswap_urls_pattern_count(self):
        assert len(urls.urlpatterns) == 1

    def test_inhouse_hogswap_urls_hogswap_pattern(self):
        url = urls.urlpatterns[0]
        assert isinstance(url, URLPattern)
        assert url.lookup_str == "widgets.inhouse.hogswap.views.HogswapSwapView"
        assert str(url.pattern) == r"^(\w{40}|\w{58})$"

    def test_inhouse_hogswap_urls_name_matches_the_widget_id(self):
        """`swap_entry_url` reverses a router's shell by its own widget id.

        A name that does not match makes the router selectable on the settings
        page and unreachable from every swap button, which is a failure with no
        error message anywhere.
        """
        from widgets.inhouse.hogswap.manifest import MANIFEST

        assert urls.urlpatterns[0].name == MANIFEST.id == "hogswap"
