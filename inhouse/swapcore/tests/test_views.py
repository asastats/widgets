"""Testing module for :py:mod:`widgets.inhouse.swapcore.views` module."""

from widgets.inhouse.swapcore.views import SwapAssetsView, SwapHoldingsView


class TestInhouseSwapcoreViewsSwapHoldingsView:
    """Testing class for :py:class:`widgets.inhouse.swapcore.views.SwapHoldingsView`."""

    def test_inhouse_swapcore_views_swap_holdings_view_test_func_passes(self, mocker):
        view = SwapHoldingsView()
        view.args = ["addr_one"]
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        view.request = mocker.MagicMock()
        linked = mocker.patch(
            "widgets.inhouse.swapcore.views.is_linked_to_user", return_value=True
        )
        assert view.test_func() is True
        assert view.address == "ADDR_ONE"
        gate.assert_called_once_with(1)
        linked.assert_called_once_with(view.request.user, "ADDR_ONE")

    def test_inhouse_swapcore_views_swap_holdings_view_test_func_unlinked(self, mocker):
        view = SwapHoldingsView()
        view.args = ["addr_one"]
        mocker.patch.object(view, "manifest_test_func", return_value=True)
        view.request = mocker.MagicMock()
        mocker.patch(
            "widgets.inhouse.swapcore.views.is_linked_to_user", return_value=False
        )
        assert view.test_func() is False

    def test_inhouse_swapcore_views_swap_holdings_view_test_func_no_permission(
        self, mocker
    ):
        view = SwapHoldingsView()
        view.args = ["addr_one"]
        mocker.patch.object(view, "manifest_test_func", return_value=False)
        linked = mocker.patch("widgets.inhouse.swapcore.views.is_linked_to_user")
        assert view.test_func() is False
        linked.assert_not_called()

    def test_inhouse_swapcore_views_swap_holdings_view_get_context_data(self, mocker):
        import json

        view = SwapHoldingsView()
        view.request = mocker.MagicMock()
        view.address = "ADDR_ONE"
        # Backend returns {asset_id: {name, unit, decimals, amount}} (id 0 = ALGO).
        data = {
            "31566704": {
                "name": "USD Coin",
                "unit": "USDC",
                "decimals": 6,
                "amount": 7,
            },
            "0": {"name": "Algorand", "unit": "ALGO", "decimals": 6, "amount": 5},
        }
        fetch = mocker.patch(
            "widgets.inhouse.swapcore.views.fetch_account_holdings", return_value=data
        )
        context = view.get_context_data()
        fetch.assert_called_once_with(
            "ADDR_ONE", SwapHoldingsView.manifest.engine_endpoints
        )
        # Flattened, id-sorted, with the id folded in (ALGO first).
        expected = [
            {"name": "Algorand", "unit": "ALGO", "decimals": 6, "amount": 5, "id": 0},
            {
                "name": "USD Coin",
                "unit": "USDC",
                "decimals": 6,
                "amount": 7,
                "id": 31566704,
            },
        ]
        assert context["address"] == "ADDR_ONE"
        assert context["holdings"] == expected
        assert json.loads(context["holdings_json"]) == expected
        # The shared view does NOT emit router_id -- the panel doesn't read it.
        assert "router_id" not in context


class TestInhouseSwapcoreViewsSwapAssetsView:
    """Testing class for :py:class:`widgets.inhouse.swapcore.views.SwapAssetsView`."""

    def test_inhouse_swapcore_views_swap_assets_view_test_func(self, mocker):
        view = SwapAssetsView()
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        gate.assert_called_once_with(1)

    def test_inhouse_swapcore_views_swap_assets_view_get_context_data_query(
        self, mocker
    ):
        view = SwapAssetsView()
        view.request = mocker.MagicMock()
        view.request.GET.get.return_value = "usdc"
        assets = [{"id": 31566704, "unit": "USDC", "name": "USD Coin", "decimals": 6}]
        fetch = mocker.patch(
            "widgets.inhouse.swapcore.views.fetch_asset_matches", return_value=assets
        )
        context = view.get_context_data()
        fetch.assert_called_once_with("usdc", SwapAssetsView.manifest.engine_endpoints)
        assert context["query"] == "usdc"
        assert context["assets"] == assets

    def test_inhouse_swapcore_views_swap_assets_view_get_context_data_empty(
        self, mocker
    ):
        view = SwapAssetsView()
        view.request = mocker.MagicMock()
        view.request.GET.get.return_value = "  "
        fetch = mocker.patch("widgets.inhouse.swapcore.views.fetch_asset_matches")
        context = view.get_context_data()
        fetch.assert_not_called()
        assert context["query"] == ""
        assert context["assets"] == []
