"""Testing module for :py:mod:`widgets.inhouse.hogswap.views` module."""

from types import SimpleNamespace

from widgets.inhouse.hogswap.views import HogswapSwapView


class TestInhouseHogswapViewsHogswapSwapView:
    """Testing class for :py:class:`widgets.inhouse.hogswap.views.HogswapSwapView`."""

    def test_inhouse_hogswap_views_hogswap_swap_view_attrs(self):
        assert HogswapSwapView.template_name == "hogswap/index.html"
        assert HogswapSwapView.manifest.id == "hogswap"

    def test_inhouse_hogswap_views_hogswap_swap_view_is_a_swap_router(self):
        """`category = "swap"` is what puts it on the settings page.

        `widgethost.registry.swap_routers` discovers routers by this and
        nothing else, so the manifest is the whole registration.
        """
        assert HogswapSwapView.manifest.category == "swap"

    def test_inhouse_hogswap_views_hogswap_swap_view_client_cfg_context(self, mocker):
        view = HogswapSwapView()
        mocker.patch(
            "widgets.inhouse.hogswap.views.settings",
            SimpleNamespace(
                HOGSWAP_BASE_URL="https://staging.example", HOGSWAP_API_KEY="hsk_test"
            ),
        )
        assert view.client_cfg_context() == {
            "hogswap_base_url": "https://staging.example",
            "hogswap_api_key": "hsk_test",
        }

    def test_inhouse_hogswap_views_hogswap_swap_view_client_cfg_context_defaults(
        self, mocker
    ):
        """Both are optional: empty means the SDK default host and no key.

        The free tier needs neither, so a deployment that configures nothing
        must still produce a working widget rather than an unconfigured one.
        """
        view = HogswapSwapView()
        mocker.patch("widgets.inhouse.hogswap.views.settings", SimpleNamespace())
        assert view.client_cfg_context() == {
            "hogswap_base_url": "",
            "hogswap_api_key": "",
        }
