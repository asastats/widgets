"""Testing module for :py:mod:`widgets.inhouse.folks.views` module."""

from django.conf import settings
from widgethost.swap_views import (
    BaseSwapAssetsView,
    BaseSwapHoldingsView,
    BaseSwapShellView,
)
from widgets.inhouse.folks.manifest import MANIFEST
from widgets.inhouse.folks.views import (
    FolksAssetsView,
    FolksHoldingsView,
    FolksSwapView,
)


class TestInhouseFolksViewsFolksSwapView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksSwapView`."""

    def test_inhouse_folks_views_folks_swap_view_is_subclass_of_baseswapshellview(self):
        assert issubclass(FolksSwapView, BaseSwapShellView)

    def test_inhouse_folks_views_folks_swap_view_class_variables(self):
        assert FolksSwapView.template_name == "folks/index.html"
        assert FolksSwapView.manifest is MANIFEST

    def test_inhouse_folks_views_folks_swap_view_client_cfg_context_functionality(self):
        assert FolksSwapView().client_cfg_context() == {
            "folks_network": getattr(settings, "FOLKS_NETWORK", "mainnet"),
            "folks_referrer": getattr(settings, "FOLKS_REFERRER_ADDRESS", ""),
            "folks_fee_bps": getattr(settings, "FOLKS_FEE_BPS", 0),
        }


class TestInhouseFolksViewsFolksHoldingsView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksHoldingsView`."""

    def test_inhouse_folks_views_folks_holdings_view_subclass_of_baseswapholdingsview(
        self,
    ):
        assert issubclass(FolksHoldingsView, BaseSwapHoldingsView)

    def test_inhouse_folks_views_folks_holdings_view_class_variables(self):
        assert FolksHoldingsView.template_name == "folks/_panel.html"
        assert FolksHoldingsView.manifest is MANIFEST


class TestInhouseFolksViewsFolksAssetsView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksAssetsView`."""

    def test_inhouse_folks_views_folks_holdings_view_is_subclass_of_baseswapassetsview(
        self,
    ):
        assert issubclass(FolksAssetsView, BaseSwapAssetsView)

    def test_inhouse_folks_views_folks_assets_view_class_variables(self):
        assert FolksAssetsView.template_name == "folks/_assets.html"
        assert FolksAssetsView.manifest is MANIFEST
