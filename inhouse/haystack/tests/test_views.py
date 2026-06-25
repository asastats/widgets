"""Testing module for :py:mod:`widgets.inhouse.haystack.views` module."""

from django.conf import settings
from widgethost.swap_views import (
    BaseSwapAssetsView,
    BaseSwapHoldingsView,
    BaseSwapShellView,
)
from widgets.inhouse.haystack.manifest import MANIFEST
from widgets.inhouse.haystack.views import (
    HaystackAssetsView,
    HaystackHoldingsView,
    HaystackSwapView,
)


class TestInhouseHaystackViewsHaystackSwapView:
    """Testing class for :py:class:`widgets.inhouse.haystack.views.HaystackSwapView`."""

    def test_inhouse_haystack_views_haystack_swap_view_is_subclass_of_baseswapshellview(
        self,
    ):
        assert issubclass(HaystackSwapView, BaseSwapShellView)

    def test_inhouse_haystack_views_haystack_swap_view_class_variables(self):
        assert HaystackSwapView.template_name == "haystack/index.html"
        assert HaystackSwapView.manifest is MANIFEST

    def test_inhouse_haystack_views_haystack_swap_view_client_cfg_context_functionality(
        self,
    ):
        assert HaystackSwapView().client_cfg_context() == {
            "haystack_referrer": getattr(settings, "HAYSTACK_REFERRER_ADDRESS", ""),
            "haystack_api_key": getattr(settings, "HAYSTACK_API_KEY", ""),
        }


class TestInhouseHaystackViewsHaystackHoldingsView:
    """Testing class for :py:class:`widgets.inhouse.haystack.views.HaystackHoldingsView`."""

    def test_inhouse_haystack_views_haystack_holdings_view_subclass_of_baseswapholdingsview(
        self,
    ):
        assert issubclass(HaystackHoldingsView, BaseSwapHoldingsView)

    def test_inhouse_haystack_views_haystack_holdings_view_class_variables(self):
        assert HaystackHoldingsView.template_name == "folks/_panel.html"
        assert HaystackHoldingsView.manifest is MANIFEST


class TestInhouseHaystackViewsHaystackAssetsView:
    """Testing class for :py:class:`widgets.inhouse.haystack.views.HaystackAssetsView`."""

    def test_inhouse_haystack_views_haystack_holdings_view_is_subclass_of_baseswapassetsview(
        self,
    ):
        assert issubclass(HaystackAssetsView, BaseSwapAssetsView)

    def test_inhouse_haystack_views_haystack_assets_view_class_variables(self):
        assert HaystackAssetsView.template_name == "folks/_assets.html"
        assert HaystackAssetsView.manifest is MANIFEST
