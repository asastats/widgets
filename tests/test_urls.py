"""Testing module for widgets app synchronous url dispatcher module."""

import importlib

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
        assert len(urls.urlpatterns) == 4


class TestWidgetsUrlsFallback:
    """Testing the bare-import fallback in :py:mod:`widgets.urls`."""

    def test_widgets_urls_falls_back_to_bare_imports(self, mocker):
        def fake_include(arg):
            if arg.startswith("widgets."):
                raise ModuleNotFoundError(arg)
            return ("include", arg)

        mocker.patch("django.urls.include", side_effect=fake_include)
        mocker.patch("django.urls.re_path", side_effect=lambda pat, inc: ("re", inc))
        try:
            importlib.reload(urls)
            assert urls.urlpatterns == [
                ("re", ("include", "inhouse.historic.urls")),
                ("re", ("include", "inhouse.folks.urls")),
                ("re", ("include", "inhouse.haystack.urls")),
                ("re", ("include", "inhouse.swapcore.urls")),
            ]
        finally:
            mocker.stopall()
            importlib.reload(urls)
